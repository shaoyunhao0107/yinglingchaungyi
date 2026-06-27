package apiserver

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"

	"monica-proxy/internal/errors"
	"monica-proxy/internal/service"

	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
	"github.com/sashabaranov/go-openai"
)// AnthropicRequest Anthropic Messages API 请求结构
type AnthropicRequest struct {
	Model       string             `json:"model"`
	Messages    []AnthropicMessage `json:"messages"`
	System      interface{}        `json:"system"`
	MaxTokens   int                `json:"max_tokens"`
	Temperature *float32           `json:"temperature"`
	Stream      bool               `json:"stream"`
	Tools       []AnthropicTool    `json:"tools,omitempty"`
	ToolChoice  interface{}        `json:"tool_choice,omitempty"`
}

type AnthropicMessage struct {
	Role    string      `json:"role"`
	Content interface{} `json:"content"`
}

// AnthropicContentPart 支持 text / tool_use / tool_result
type AnthropicContentPart struct {
	Type      string          `json:"type"`
	Text      string          `json:"text,omitempty"`
	ID        string          `json:"id,omitempty"`
	Name      string          `json:"name,omitempty"`
	Input     json.RawMessage `json:"input,omitempty"`
	ToolUseID string          `json:"tool_use_id,omitempty"`
	Content   interface{}     `json:"content,omitempty"`
}

type AnthropicTool struct {
	Name        string          `json:"name"`
	Description string          `json:"description,omitempty"`
	InputSchema json.RawMessage `json:"input_schema"`
}

type AnthropicResponse struct {
	ID           string                 `json:"id"`
	Type         string                 `json:"type"`
	Role         string                 `json:"role"`
	Model        string                 `json:"model"`
	Content      []AnthropicContentPart `json:"content"`
	StopReason   string                 `json:"stop_reason"`
	StopSequence *string                `json:"stop_sequence"`
	Usage        AnthropicUsage         `json:"usage"`
}

type AnthropicUsage struct {
	InputTokens  int `json:"input_tokens"`
	OutputTokens int `json:"output_tokens"`
}

func parseContentParts(content interface{}) []AnthropicContentPart {
	switch v := content.(type) {
	case string:
		return []AnthropicContentPart{{Type: "text", Text: v}}
	case []interface{}:
		var parts []AnthropicContentPart
		for _, item := range v {
			b, err := json.Marshal(item)
			if err != nil {
				continue
			}
			var p AnthropicContentPart
			if err := json.Unmarshal(b, &p); err != nil {
				continue
			}
			parts = append(parts, p)
		}
		return parts
	}
	return nil
}

func anthropicContentToString(content interface{}) string {
	var result string
	for _, p := range parseContentParts(content) {
		if p.Type == "text" {
			result += p.Text
		}
	}
	return result
}

func anthropicToChatRequest(r *AnthropicRequest) (*openai.ChatCompletionRequest, error) {
	var messages []openai.ChatCompletionMessage

	sysText := ""
	if r.System != nil {
		sysText = anthropicContentToString(r.System)
	}
	// 如果请求携带 tools，追加强制调用工具的指令
	if len(r.Tools) > 0 {
		toolPrompt := "You have tools available. When the user asks you to perform a task that requires using a tool (such as running commands, reading/writing files, or browsing), you MUST call the appropriate tool. Do NOT describe the steps in plain text — actually call the tool."
		if sysText != "" {
			sysText = sysText + "\n\n" + toolPrompt
		} else {
			sysText = toolPrompt
		}
	}
	if sysText != "" {
		messages = append(messages, openai.ChatCompletionMessage{
			Role:    openai.ChatMessageRoleSystem,
			Content: sysText,
		})
	}

	for _, msg := range r.Messages {
		parts := parseContentParts(msg.Content)
		role := msg.Role
		if role == "" {
			role = openai.ChatMessageRoleUser
		}
		switch role {
		case openai.ChatMessageRoleAssistant:
			var textContent string
			var toolCalls []openai.ToolCall
			for _, p := range parts {
				switch p.Type {
				case "text":
					textContent += p.Text
				case "tool_use":
					inputStr := "{}"
					if len(p.Input) > 0 {
						inputStr = string(p.Input)
					}
					toolCalls = append(toolCalls, openai.ToolCall{
						ID:   p.ID,
						Type: openai.ToolTypeFunction,
						Function: openai.FunctionCall{
							Name:      p.Name,
							Arguments: inputStr,
						},
					})
				}
			}
			messages = append(messages, openai.ChatCompletionMessage{
				Role:      openai.ChatMessageRoleAssistant,
				Content:   textContent,
				ToolCalls: toolCalls,
			})
		case openai.ChatMessageRoleUser:
			hasToolResult := false
			for _, p := range parts {
				if p.Type == "tool_result" {
					hasToolResult = true
					var resultText string
					switch v := p.Content.(type) {
					case string:
						resultText = v
					default:
						b, _ := json.Marshal(p.Content)
						resultText = string(b)
					}
					messages = append(messages, openai.ChatCompletionMessage{
						Role:       openai.ChatMessageRoleTool,
						Content:    resultText,
						ToolCallID: p.ToolUseID,
					})
				}
			}
			if !hasToolResult {
				messages = append(messages, openai.ChatCompletionMessage{
					Role:    openai.ChatMessageRoleUser,
					Content: anthropicContentToString(msg.Content),
				})
			}
		default:
			messages = append(messages, openai.ChatCompletionMessage{
				Role:    role,
				Content: anthropicContentToString(msg.Content),
			})
		}
	}

	if len(messages) == 0 {
		return nil, errors.NewBadRequestError("messages cannot be empty", nil)
	}

	chatReq := &openai.ChatCompletionRequest{
		Model:    r.Model,
		Messages: messages,
		Stream:   r.Stream,
	}
	if r.Temperature != nil {
		chatReq.Temperature = *r.Temperature
	}
	if r.MaxTokens > 0 {
		chatReq.MaxTokens = r.MaxTokens
	}
	for _, t := range r.Tools {
		chatReq.Tools = append(chatReq.Tools, openai.Tool{
			Type: openai.ToolTypeFunction,
			Function: &openai.FunctionDefinition{
				Name:        t.Name,
				Description: t.Description,
				Parameters:  t.InputSchema,
			},
		})
	}
	if r.ToolChoice != nil {
		switch v := r.ToolChoice.(type) {
		case string:
			switch v {
			case "any":
				chatReq.ToolChoice = "required"
			case "auto":
				chatReq.ToolChoice = "auto"
			case "none":
				chatReq.ToolChoice = "none"
			}
		case map[string]interface{}:
			if name, ok := v["name"].(string); ok {
				chatReq.ToolChoice = openai.ToolChoice{
					Type:     openai.ToolTypeFunction,
					Function: openai.ToolFunction{Name: name},
				}
			}
		}
	}
	return chatReq, nil
}

func chatCompletionToAnthropic(comp *openai.ChatCompletionResponse) *AnthropicResponse {
	resp := &AnthropicResponse{
		ID:         "msg_" + uuid.New().String(),
		Type:       "message",
		Role:       "assistant",
		Model:      comp.Model,
		Content:    []AnthropicContentPart{},
		StopReason: "end_turn",
		Usage: AnthropicUsage{
			InputTokens:  comp.Usage.PromptTokens,
			OutputTokens: comp.Usage.CompletionTokens,
		},
	}
	for _, choice := range comp.Choices {
		if choice.Message.Content != "" {
			resp.Content = append(resp.Content, AnthropicContentPart{
				Type: "text",
				Text: choice.Message.Content,
			})
		}
		if len(choice.Message.ToolCalls) > 0 {
			resp.StopReason = "tool_use"
			for _, tc := range choice.Message.ToolCalls {
				inputRaw := json.RawMessage("{}")
				if tc.Function.Arguments != "" {
					inputRaw = json.RawMessage(tc.Function.Arguments)
				}
				resp.Content = append(resp.Content, AnthropicContentPart{
					Type:  "tool_use",
					ID:    tc.ID,
					Name:  tc.Function.Name,
					Input: inputRaw,
				})
			}
		}
		if choice.FinishReason == "length" {
			resp.StopReason = "max_tokens"
		}
	}
	return resp
}

func writeAnthropicSSE(w io.Writer, eventType string, payload interface{}) error {
	b, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	_, err = fmt.Fprintf(w, "event: %s\ndata: %s\n\n", eventType, b)
	return err
}

type openaiStreamDelta struct {
	Choices []struct {
		Delta struct {
			Role      string `json:"role"`
			Content   string `json:"content"`
			ToolCalls []struct {
				Index    int    `json:"index"`
				ID       string `json:"id"`
				Type     string `json:"type"`
				Function struct {
					Name      string `json:"name"`
					Arguments string `json:"arguments"`
				} `json:"function"`
			} `json:"tool_calls"`
		} `json:"delta"`
		FinishReason string `json:"finish_reason"`
	} `json:"choices"`
}

type monicaStreamData struct {
	Text     string `json:"text"`
	Finished bool   `json:"finished"`
	Error    *struct {
		Code int    `json:"code"`
		Msg  string `json:"msg"`
	} `json:"error"`
}

func streamMonicaToAnthropicAPI(model string, w io.Writer, r io.Reader) error {
	flusher, _ := w.(http.Flusher)
	flush := func() {
		if flusher != nil {
			flusher.Flush()
		}
	}

	msgID := "msg_" + uuid.New().String()

	if err := writeAnthropicSSE(w, "message_start", map[string]interface{}{
		"type": "message_start",
		"message": map[string]interface{}{
			"id":            msgID,
			"type":          "message",
			"role":          "assistant",
			"model":         model,
			"content":       []interface{}{},
			"stop_reason":   nil,
			"stop_sequence": nil,
			"usage":         map[string]interface{}{"input_tokens": 0, "output_tokens": 0},
		},
	}); err != nil {
		return err
	}
	if err := writeAnthropicSSE(w, "ping", map[string]interface{}{"type": "ping"}); err != nil {
		return err
	}
	flush()

	const dataPrefix = "data: "
	const dataPrefixLen = len(dataPrefix)

	type toolBlockState struct {
		index int
		id    string
		name  string
	}

	textBlockOpened := false
	textBlockIndex := -1
	toolBlocks := map[int]*toolBlockState{}
	nextBlockIndex := 0
	stopReason := "end_turn"

	openTextBlock := func() error {
		if textBlockOpened {
			return nil
		}
		textBlockIndex = nextBlockIndex
		nextBlockIndex++
		textBlockOpened = true
		return writeAnthropicSSE(w, "content_block_start", map[string]interface{}{
			"type":          "content_block_start",
			"index":         textBlockIndex,
			"content_block": map[string]interface{}{"type": "text", "text": ""},
		})
	}

	scanner := bufio.NewScanner(r)
	for scanner.Scan() {
		line := scanner.Bytes()
		if !bytes.HasPrefix(line, []byte(dataPrefix)) {
			continue
		}
		jsonBytes := line[dataPrefixLen:]
		if len(jsonBytes) == 0 || bytes.Equal(jsonBytes, []byte("[DONE]")) {
			break
		}

		// 尝试 OpenAI stream chunk 格式
		var oaiChunk openaiStreamDelta
		if json.Unmarshal(jsonBytes, &oaiChunk) == nil && len(oaiChunk.Choices) > 0 {
			choice := oaiChunk.Choices[0]
			if choice.FinishReason != "" {
				if choice.FinishReason == "tool_calls" {
					stopReason = "tool_use"
				} else if choice.FinishReason == "length" {
					stopReason = "max_tokens"
				}
			}
			if choice.Delta.Content != "" {
				if err := openTextBlock(); err != nil {
					return err
				}
				if err := writeAnthropicSSE(w, "content_block_delta", map[string]interface{}{
					"type":  "content_block_delta",
					"index": textBlockIndex,
					"delta": map[string]interface{}{"type": "text_delta", "text": choice.Delta.Content},
				}); err != nil {
					return err
				}
				flush()
			}
			for _, tc := range choice.Delta.ToolCalls {
				idx := tc.Index
				if _, exists := toolBlocks[idx]; !exists {
					blockIdx := nextBlockIndex
					nextBlockIndex++
					toolBlocks[idx] = &toolBlockState{index: blockIdx, id: tc.ID, name: tc.Function.Name}
					stopReason = "tool_use"
					if err := writeAnthropicSSE(w, "content_block_start", map[string]interface{}{
						"type":  "content_block_start",
						"index": blockIdx,
						"content_block": map[string]interface{}{
							"type":  "tool_use",
							"id":    tc.ID,
							"name":  tc.Function.Name,
							"input": map[string]interface{}{},
						},
					}); err != nil {
						return err
					}
					flush()
				}
				if tc.Function.Arguments != "" {
					blockIdx := toolBlocks[idx].index
					if err := writeAnthropicSSE(w, "content_block_delta", map[string]interface{}{
						"type":  "content_block_delta",
						"index": blockIdx,
						"delta": map[string]interface{}{"type": "input_json_delta", "partial_json": tc.Function.Arguments},
					}); err != nil {
						return err
					}
					flush()
				}
			}
			continue
		}

		// 降级：Monica 原生格式
		var md monicaStreamData
		if err := json.Unmarshal(jsonBytes, &md); err != nil {
			continue
		}
		if md.Error != nil {
			return fmt.Errorf("monica error %d: %s", md.Error.Code, md.Error.Msg)
		}
		if md.Text != "" {
			if err := openTextBlock(); err != nil {
				return err
			}
			if err := writeAnthropicSSE(w, "content_block_delta", map[string]interface{}{
				"type":  "content_block_delta",
				"index": textBlockIndex,
				"delta": map[string]interface{}{"type": "text_delta", "text": md.Text},
			}); err != nil {
				return err
			}
			flush()
		}
	}

	if err := scanner.Err(); err != nil && err != io.EOF {
		return err
	}

	// 关闭 text block
	if textBlockOpened {
		if err := writeAnthropicSSE(w, "content_block_stop", map[string]interface{}{
			"type":  "content_block_stop",
			"index": textBlockIndex,
		}); err != nil {
			return err
		}
	}
	// 关闭所有 tool blocks
	for _, tb := range toolBlocks {
		if err := writeAnthropicSSE(w, "content_block_stop", map[string]interface{}{
			"type":  "content_block_stop",
			"index": tb.index,
		}); err != nil {
			return err
		}
	}

	// message_delta
	if err := writeAnthropicSSE(w, "message_delta", map[string]interface{}{
		"type": "message_delta",
		"delta": map[string]interface{}{
			"stop_reason":   stopReason,
			"stop_sequence": nil,
		},
		"usage": map[string]interface{}{"output_tokens": 0},
	}); err != nil {
		return err
	}
	// message_stop
	if err := writeAnthropicSSE(w, "message_stop", map[string]interface{}{"type": "message_stop"}); err != nil {
		return err
	}
	flush()
	return nil
}

// createAnthropicHandler 创建 Anthropic Messages API 处理器
func createAnthropicHandler(chatService service.ChatService) echo.HandlerFunc {
	return func(c echo.Context) error {
		var req AnthropicRequest
		if err := c.Bind(&req); err != nil {
			return c.JSON(http.StatusBadRequest, map[string]string{"error": err.Error()})
		}

		chatReq, err := anthropicToChatRequest(&req)
		if err != nil {
			return c.JSON(http.StatusBadRequest, map[string]string{"error": err.Error()})
		}

		if req.Stream {
			c.Response().Header().Set("Content-Type", "text/event-stream")
			c.Response().Header().Set("Cache-Control", "no-cache")
			c.Response().Header().Set("Connection", "keep-alive")
			c.Response().WriteHeader(http.StatusOK)

			pr, pw := io.Pipe()
			go func() {
				defer pw.Close()
				if err := chatService.StreamChat(c.Request().Context(), chatReq, pw); err != nil {
					_ = err
				}
			}()
			return streamMonicaToAnthropicAPI(req.Model, c.Response(), pr)
		}

		comp, err := chatService.Chat(c.Request().Context(), chatReq)
		if err != nil {
			return c.JSON(http.StatusInternalServerError, map[string]string{"error": err.Error()})
		}
		return c.JSON(http.StatusOK, chatCompletionToAnthropic(comp))
	}
}
