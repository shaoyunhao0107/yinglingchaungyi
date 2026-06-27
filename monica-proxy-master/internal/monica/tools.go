package monica

import (
	"encoding/json"
	"fmt"
	"regexp"
	"strings"

	"github.com/google/uuid"
	"github.com/sashabaranov/go-openai"
)

// BuildToolSystemPrompt 构建工具调用的 system prompt
// 使用纯文本格式避免触发 Monica 内容过滤
func BuildToolSystemPrompt(tools []openai.Tool) string {
	if len(tools) == 0 {
		return ""
	}
	var sb strings.Builder
	sb.WriteString("You have tools available. When calling a tool, output exactly one line in this format:\n")
	sb.WriteString("TOOL_CALL: {\"name\": \"TOOL_NAME\", \"arguments\": {ARGS_JSON}}\n")
	sb.WriteString("Do not add explanation. After receiving the tool result, continue normally.\n\n")
	sb.WriteString("Tools:\n")
	for _, t := range tools {
		if t.Function == nil {
			continue
		}
		sb.WriteString(fmt.Sprintf("- %s", t.Function.Name))
		if t.Function.Description != "" {
			sb.WriteString(": " + t.Function.Description)
		}
		sb.WriteString("\n")
		if t.Function.Parameters != nil {
			paramBytes, err := json.Marshal(t.Function.Parameters)
			if err == nil {
				sb.WriteString(fmt.Sprintf("  params: %s\n", string(paramBytes)))
			}
		}
	}
	return sb.String()
}

// toolCallLineRegex 匹配 TOOL_CALL: {...} 格式
var toolCallLineRegex = regexp.MustCompile(`(?m)^TOOL_CALL:\s*({.+})\s*$`)

type toolCallJSON struct {
	Name      string          `json:"name"`
	Arguments json.RawMessage `json:"arguments"`
}

// ParseToolCallsFromText 从模型输出文本中解析工具调用
func ParseToolCallsFromText(text string) (remaining string, toolCalls []openai.ToolCall, found bool) {
	matches := toolCallLineRegex.FindAllStringSubmatchIndex(text, -1)
	if len(matches) == 0 {
		return text, nil, false
	}
	var textParts []string
	lastEnd := 0
	for _, loc := range matches {
		textParts = append(textParts, text[lastEnd:loc[0]])
		lastEnd = loc[1]
		jsonStr := text[loc[2]:loc[3]]
		var tcj toolCallJSON
		if err := json.Unmarshal([]byte(jsonStr), &tcj); err != nil {
			continue
		}
		argStr := "{}"
		if len(tcj.Arguments) > 0 {
			argStr = string(tcj.Arguments)
		}
		toolCalls = append(toolCalls, openai.ToolCall{
			ID:   "call_" + uuid.New().String()[:8],
			Type: openai.ToolTypeFunction,
			Function: openai.FunctionCall{
				Name:      tcj.Name,
				Arguments: argStr,
			},
		})
	}
	textParts = append(textParts, text[lastEnd:])
	remaining = strings.TrimSpace(strings.Join(textParts, ""))
	return remaining, toolCalls, true
}

// BuildToolCallsStreamChunks 将 tool_calls 转成 OpenAI SSE 流式 chunks
func BuildToolCallsStreamChunks(model, chatID string, created int64, toolCalls []openai.ToolCall) []string {
	var chunks []string
	for i, tc := range toolCalls {
		idxCopy := i
		startChunk := map[string]interface{}{
			"id":      "chatcmpl-" + chatID,
			"object":  sseObject,
			"created": created,
			"model":   model,
			"choices": []map[string]interface{}{
				{
					"index": 0,
					"delta": map[string]interface{}{
						"tool_calls": []map[string]interface{}{
							{
								"index": idxCopy,
								"id":    tc.ID,
								"type":  "function",
								"function": map[string]interface{}{
									"name":      tc.Function.Name,
									"arguments": "",
								},
							},
						},
					},
					"finish_reason": nil,
				},
			},
		}
		b, _ := json.Marshal(startChunk)
		chunks = append(chunks, "data: "+string(b)+"\n\n")
		argChunk := map[string]interface{}{
			"id":      "chatcmpl-" + chatID,
			"object":  sseObject,
			"created": created,
			"model":   model,
			"choices": []map[string]interface{}{
				{
					"index": 0,
					"delta": map[string]interface{}{
						"tool_calls": []map[string]interface{}{
							{
								"index": idxCopy,
								"function": map[string]interface{}{
									"arguments": tc.Function.Arguments,
								},
							},
						},
					},
					"finish_reason": nil,
				},
			},
		}
		b2, _ := json.Marshal(argChunk)
		chunks = append(chunks, "data: "+string(b2)+"\n\n")
	}
	finishChunk := map[string]interface{}{
		"id":      "chatcmpl-" + chatID,
		"object":  sseObject,
		"created": created,
		"model":   model,
		"choices": []map[string]interface{}{
			{
				"index":         0,
				"delta":         map[string]interface{}{},
				"finish_reason": "tool_calls",
			},
		},
	}
	b3, _ := json.Marshal(finishChunk)
	chunks = append(chunks, "data: "+string(b3)+"\n\n")
	chunks = append(chunks, "data: [DONE]\n\n")
	return chunks
}
