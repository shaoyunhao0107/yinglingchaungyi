package apiserver

import (
	"bufio"
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"

	"monica-proxy/internal/errors"
	"monica-proxy/internal/service"

	"github.com/google/uuid"
	"github.com/labstack/echo/v4"
	"github.com/sashabaranov/go-openai"
)

// ResponsesRequest 对应 /v1/responses 请求体（先实现常用字段）
type ResponsesRequest struct {
	Model           string      `json:"model"`
	Input           interface{} `json:"input"`
	Instructions    string      `json:"instructions"`
	Temperature     *float32    `json:"temperature"`
	MaxOutputTokens int         `json:"max_output_tokens"`
	Stream          bool        `json:"stream"`
}

// ResponsesResponse 对应 /v1/responses 非流式响应
type ResponsesResponse struct {
	ID        string                `json:"id"`
	Object    string                `json:"object"`
	CreatedAt int64                 `json:"created_at"`
	Model     string                `json:"model"`
	Status    string                `json:"status"`
	Output    []ResponsesOutputItem `json:"output"`
	Usage     *ResponsesUsage       `json:"usage,omitempty"`
}

type ResponsesOutputItem struct {
	Type    string                 `json:"type"`
	ID      string                 `json:"id"`
	Status  string                 `json:"status"`
	Role    string                 `json:"role"`
	Content []ResponsesContentPart `json:"content"`
}

type ResponsesContentPart struct {
	Type string `json:"type"`
	Text string `json:"text"`
}

type ResponsesUsage struct {
	InputTokens  int `json:"input_tokens"`
	OutputTokens int `json:"output_tokens"`
	TotalTokens  int `json:"total_tokens"`
}

func responsesToChatRequest(r *ResponsesRequest) (*openai.ChatCompletionRequest, error) {
	var messages []openai.ChatCompletionMessage

	if r.Instructions != "" {
		messages = append(messages, openai.ChatCompletionMessage{
			Role:    openai.ChatMessageRoleSystem,
			Content: r.Instructions,
		})
	}

	switch v := r.Input.(type) {
	case string:
		messages = append(messages, openai.ChatCompletionMessage{
			Role:    openai.ChatMessageRoleUser,
			Content: v,
		})
	case []interface{}:
		for _, item := range v {
			m, ok := item.(map[string]interface{})
			if !ok {
				continue
			}
			role, _ := m["role"].(string)
			if role == "" {
				role = openai.ChatMessageRoleUser
			}
			// content 可能是 string，也可能是 [{type:"input_text",text:"..."}] 数组
			var contentStr string
			switch cv := m["content"].(type) {
			case string:
				contentStr = cv
			case []interface{}:
				// Cherry Studio / Responses API 格式：content 是 part 数组
				for _, part := range cv {
					if pm, ok := part.(map[string]interface{}); ok {
						if t, _ := pm["type"].(string); t == "input_text" || t == "text" || t == "output_text" {
							if txt, ok := pm["text"].(string); ok {
								contentStr += txt
							}
						}
					}
				}
			}
			if contentStr != "" {
				messages = append(messages, openai.ChatCompletionMessage{Role: role, Content: contentStr})
			}
		}
	default:
		return nil, errors.NewBadRequestError("input 格式不支持，需为 string 或消息数组", nil)
	}

	if len(messages) == 0 {
		return nil, errors.NewBadRequestError("input不能为空", nil)
	}

	chatReq := &openai.ChatCompletionRequest{
		Model:    r.Model,
		Messages: messages,
		Stream:   r.Stream,
	}
	if r.Temperature != nil {
		chatReq.Temperature = *r.Temperature
	}
	if r.MaxOutputTokens > 0 {
		chatReq.MaxTokens = r.MaxOutputTokens
	}
	return chatReq, nil
}

func chatCompletionToResponses(comp *openai.ChatCompletionResponse) *ResponsesResponse {
	resp := &ResponsesResponse{
		ID:        "resp_" + uuid.New().String(),
		Object:    "response",
		CreatedAt: time.Now().Unix(),
		Model:     comp.Model,
		Status:    "completed",
		Output:    []ResponsesOutputItem{},
	}

	for _, choice := range comp.Choices {
		resp.Output = append(resp.Output, ResponsesOutputItem{
			Type:   "message",
			ID:     "msg_" + uuid.New().String(),
			Status: "completed",
			Role:   choice.Message.Role,
			Content: []ResponsesContentPart{
				{Type: "output_text", Text: choice.Message.Content},
			},
		})
	}

	if comp.Usage.TotalTokens > 0 {
		resp.Usage = &ResponsesUsage{
			InputTokens:  comp.Usage.PromptTokens,
			OutputTokens: comp.Usage.CompletionTokens,
			TotalTokens:  comp.Usage.TotalTokens,
		}
	}

	return resp
}

func writeResponsesSSE(w io.Writer, eventType string, payload interface{}) error {
	b, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	_, err = fmt.Fprintf(w, "event: %s\ndata: %s\n\n", eventType, b)
	return err
}

// 将 Monica 的 SSE（data: {...text...}）转换为 Responses API 流式事件
func streamMonicaToResponsesAPI(model string, w io.Writer, r io.Reader) error {
	flusher, _ := w.(http.Flusher)
	flush := func() {
		if flusher != nil {
			flusher.Flush()
		}
	}

	respID := "resp_" + uuid.New().String()
	msgID := "msg_" + uuid.New().String()
	now := time.Now().Unix()

	// response.created
	if err := writeResponsesSSE(w, "response.created", map[string]interface{}{
		"type": "response.created",
		"response": map[string]interface{}{
			"id":         respID,
			"object":     "response",
			"created_at": now,
			"status":     "in_progress",
			"model":      model,
			"output":     []interface{}{},
		},
	}); err != nil {
		return err
	}

	// response.output_item.added
	if err := writeResponsesSSE(w, "response.output_item.added", map[string]interface{}{
		"type":         "response.output_item.added",
		"output_index": 0,
		"item": map[string]interface{}{
			"id":      msgID,
			"type":    "message",
			"status":  "in_progress",
			"role":    "assistant",
			"content": []interface{}{},
		},
	}); err != nil {
		return err
	}

	// response.content_part.added
	if err := writeResponsesSSE(w, "response.content_part.added", map[string]interface{}{
		"type":          "response.content_part.added",
		"item_id":       msgID,
		"output_index":  0,
		"content_index": 0,
		"part": map[string]interface{}{
			"type": "output_text",
			"text": "",
		},
	}); err != nil {
		return err
	}
	flush()

	const dataPrefix = "data: "
	const dataPrefixLen = len(dataPrefix)
	var fullText string

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

		var sseData struct {
			Text        string `json:"text"`
			Finished    bool   `json:"finished"`
			AgentStatus struct {
				Type string `json:"type"`
			} `json:"agent_status"`
			Error *struct {
				Code int    `json:"code"`
				Msg  string `json:"msg"`
			} `json:"error"`
		}

		if err := json.Unmarshal(jsonBytes, &sseData); err != nil {
			continue
		}

		if sseData.AgentStatus.Type != "" {
			continue
		}
		if sseData.Error != nil {
			return fmt.Errorf("monica sse error: %d %s", sseData.Error.Code, sseData.Error.Msg)
		}

		if sseData.Text != "" {
			fullText += sseData.Text
			if err := writeResponsesSSE(w, "response.output_text.delta", map[string]interface{}{
				"type":          "response.output_text.delta",
				"item_id":       msgID,
				"output_index":  0,
				"content_index": 0,
				"delta":         sseData.Text,
			}); err != nil {
				return err
			}
			flush()
		}

		if sseData.Finished {
			break
		}
	}

	if err := scanner.Err(); err != nil {
		return err
	}

	// 收尾事件
	if err := writeResponsesSSE(w, "response.output_text.done", map[string]interface{}{
		"type":          "response.output_text.done",
		"item_id":       msgID,
		"output_index":  0,
		"content_index": 0,
		"text":          fullText,
	}); err != nil {
		return err
	}

	if err := writeResponsesSSE(w, "response.content_part.done", map[string]interface{}{
		"type":          "response.content_part.done",
		"item_id":       msgID,
		"output_index":  0,
		"content_index": 0,
		"part": map[string]interface{}{
			"type": "output_text",
			"text": fullText,
		},
	}); err != nil {
		return err
	}

	if err := writeResponsesSSE(w, "response.output_item.done", map[string]interface{}{
		"type":         "response.output_item.done",
		"output_index": 0,
		"item": map[string]interface{}{
			"id":     msgID,
			"type":   "message",
			"status": "completed",
			"role":   "assistant",
			"content": []interface{}{
				map[string]interface{}{"type": "output_text", "text": fullText},
			},
		},
	}); err != nil {
		return err
	}

	if err := writeResponsesSSE(w, "response.completed", map[string]interface{}{
		"type": "response.completed",
		"response": map[string]interface{}{
			"id":         respID,
			"object":     "response",
			"created_at": now,
			"status":     "completed",
			"model":      model,
		},
	}); err != nil {
		return err
	}

	flush()
	_, _ = io.WriteString(w, "data: [DONE]\n\n")
	flush()
	return nil
}

func createResponsesHandler(chatService service.ChatService) echo.HandlerFunc {
	return func(c echo.Context) error {
		var req ResponsesRequest
		if err := c.Bind(&req); err != nil {
			return errors.NewBadRequestError("无效的请求数据", err)
		}

		chatReq, err := responsesToChatRequest(&req)
		if err != nil {
			return err
		}

		ctx := c.Request().Context()

		if req.Stream {
			chatReq.Stream = true
			result, err := chatService.HandleChatCompletion(ctx, chatReq)
			if err != nil {
				return err
			}

			rawBody, ok := result.(io.Reader)
			if !ok {
				return errors.NewInternalError(nil)
			}
			if closer, isCloser := rawBody.(io.Closer); isCloser {
				defer closer.Close()
			}

			c.Response().Header().Set(echo.HeaderContentType, "text/event-stream")
			c.Response().Header().Set("Cache-Control", "no-cache")
			c.Response().Header().Set("Connection", "keep-alive")
			c.Response().Header().Set("Transfer-Encoding", "chunked")
			c.Response().WriteHeader(http.StatusOK)

			if err := streamMonicaToResponsesAPI(chatReq.Model, c.Response().Writer, rawBody); err != nil {
				return errors.NewInternalError(err)
			}
			return nil
		}

		chatReq.Stream = false
		result, err := chatService.HandleChatCompletion(ctx, chatReq)
		if err != nil {
			return err
		}

		comp, ok := result.(*openai.ChatCompletionResponse)
		if !ok {
			return errors.NewInternalError(nil)
		}

		return c.JSON(http.StatusOK, chatCompletionToResponses(comp))
	}
}
