package service

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"monica-proxy/internal/config"
	"monica-proxy/internal/errors"
	"monica-proxy/internal/logger"
	"monica-proxy/internal/monica"
	"monica-proxy/internal/types"
	"time"

	"github.com/sashabaranov/go-openai"
	"go.uber.org/zap"
)

// ChatService 聊天服务接口
type ChatService interface {
	HandleChatCompletion(ctx context.Context, req *openai.ChatCompletionRequest) (interface{}, error)
	Chat(ctx context.Context, req *openai.ChatCompletionRequest) (*openai.ChatCompletionResponse, error)
	StreamChat(ctx context.Context, req *openai.ChatCompletionRequest, w io.Writer) error
}

type chatService struct {
	config *config.Config
}

func NewChatService(cfg *config.Config) ChatService {
	return &chatService{config: cfg}
}

// injectToolPrompt 在请求中注入工具调用 system prompt
func injectToolPrompt(req *openai.ChatCompletionRequest) {
	if len(req.Tools) == 0 {
		return
	}
	toolPrompt := monica.BuildToolSystemPrompt(req.Tools)
	if len(req.Messages) > 0 && req.Messages[0].Role == openai.ChatMessageRoleSystem {
		req.Messages[0].Content = req.Messages[0].Content + "\n\n" + toolPrompt
	} else {
		newMessages := make([]openai.ChatCompletionMessage, 0, len(req.Messages)+1)
		newMessages = append(newMessages, openai.ChatCompletionMessage{
			Role:    openai.ChatMessageRoleSystem,
			Content: toolPrompt,
		})
		newMessages = append(newMessages, req.Messages...)
		req.Messages = newMessages
	}
}

// HandleChatCompletion 处理聊天完成请求
// 流式时统一返回已格式化的 OpenAI SSE io.Reader，由 handler 层直接 io.Copy
func (s *chatService) HandleChatCompletion(ctx context.Context, req *openai.ChatCompletionRequest) (interface{}, error) {
	if len(req.Messages) == 0 {
		return nil, errors.NewEmptyMessageError()
	}

	hasTools := len(req.Tools) > 0
	if hasTools {
		injectToolPrompt(req)
	}

	monicaReq, err := types.ChatGPTToMonica(s.config, *req)
	if err != nil {
		logger.Error("转换请求失败", zap.Error(err))
		return nil, errors.NewInternalError(err)
	}

	stream, err := monica.SendMonicaRequest(ctx, s.config, monicaReq)
	if err != nil {
		logger.Error("调用Monica API失败", zap.Error(err))
		if appErr, ok := err.(*errors.AppError); ok {
			return nil, appErr
		}
		return nil, errors.NewInternalError(err)
	}

	if req.Stream {
		// 流式：通过 pipe 将 Monica SSE 转成 OpenAI SSE，统一由 handler io.Copy
		pr, pw := io.Pipe()
		go func() {
			defer stream.RawBody().Close()
			if !hasTools {
				// 无工具：直接转换 Monica SSE -> OpenAI SSE
				if err := monica.StreamMonicaSSEToClient(req.Model, pw, stream.RawBody()); err != nil {
					pw.CloseWithError(err)
					return
				}
				pw.Close()
			} else {
				// 有工具：收集完整响应，解析 tool_calls，再写 OpenAI SSE
				response, err := monica.CollectMonicaSSEToCompletion(req.Model, stream.RawBody())
				if err != nil {
					pw.CloseWithError(err)
					return
				}
				response = applyToolCallsToResponse(response)
				if err := writeResponseAsSSE(req.Model, response, pw); err != nil {
					pw.CloseWithError(err)
					return
				}
				pw.Close()
			}
		}()
		return pr, nil
	}

	// 非流式
	defer stream.RawBody().Close()
	response, err := monica.CollectMonicaSSEToCompletion(req.Model, stream.RawBody())
	if err != nil {
		logger.Error("处理Monica响应失败", zap.Error(err))
		return nil, errors.NewInternalError(err)
	}
	if hasTools {
		response = applyToolCallsToResponse(response)
	}
	return response, nil
}

// Chat 非流式调用
func (s *chatService) Chat(ctx context.Context, req *openai.ChatCompletionRequest) (*openai.ChatCompletionResponse, error) {
	if len(req.Messages) == 0 {
		return nil, errors.NewEmptyMessageError()
	}
	hasTools := len(req.Tools) > 0
	if hasTools {
		injectToolPrompt(req)
	}
	monicaReq, err := types.ChatGPTToMonica(s.config, *req)
	if err != nil {
		logger.Error("转换请求失败", zap.Error(err))
		return nil, errors.NewInternalError(err)
	}
	stream, err := monica.SendMonicaRequest(ctx, s.config, monicaReq)
	if err != nil {
		logger.Error("调用Monica API失败", zap.Error(err))
		if appErr, ok := err.(*errors.AppError); ok {
			return nil, appErr
		}
		return nil, errors.NewInternalError(err)
	}
	defer stream.RawBody().Close()
	response, err := monica.CollectMonicaSSEToCompletion(req.Model, stream.RawBody())
	if err != nil {
		logger.Error("处理Monica响应失败", zap.Error(err))
		return nil, errors.NewInternalError(err)
	}
	if hasTools {
		response = applyToolCallsToResponse(response)
	}
	return response, nil
}

// StreamChat 流式调用（供 Anthropic handler 使用）
func (s *chatService) StreamChat(ctx context.Context, req *openai.ChatCompletionRequest, w io.Writer) error {
	if len(req.Messages) == 0 {
		return errors.NewEmptyMessageError()
	}
	hasTools := len(req.Tools) > 0
	if hasTools {
		injectToolPrompt(req)
	}
	monicaReq, err := types.ChatGPTToMonica(s.config, *req)
	if err != nil {
		logger.Error("转换请求失败", zap.Error(err))
		return errors.NewInternalError(err)
	}
	stream, err := monica.SendMonicaRequest(ctx, s.config, monicaReq)
	if err != nil {
		logger.Error("调用Monica API失败", zap.Error(err))
		if appErr, ok := err.(*errors.AppError); ok {
			return appErr
		}
		return errors.NewInternalError(err)
	}
	defer stream.RawBody().Close()
	if !hasTools {
		return monica.StreamMonicaSSEToClient(req.Model, w, stream.RawBody())
	}
	response, err := monica.CollectMonicaSSEToCompletion(req.Model, stream.RawBody())
	if err != nil {
		logger.Error("处理Monica响应失败", zap.Error(err))
		return errors.NewInternalError(err)
	}
	response = applyToolCallsToResponse(response)
	return writeResponseAsSSE(req.Model, response, w)
}

// applyToolCallsToResponse 解析响应内容中的工具调用
func applyToolCallsToResponse(resp *openai.ChatCompletionResponse) *openai.ChatCompletionResponse {
	if resp == nil || len(resp.Choices) == 0 {
		return resp
	}
	for i, choice := range resp.Choices {
		remaining, toolCalls, found := monica.ParseToolCallsFromText(choice.Message.Content)
		if found {
			resp.Choices[i].Message.Content = remaining
			resp.Choices[i].Message.ToolCalls = toolCalls
			resp.Choices[i].FinishReason = "tool_calls"
		}
	}
	return resp
}

// writeResponseAsSSE 将 ChatCompletionResponse 写成 OpenAI SSE 格式
func writeResponseAsSSE(model string, resp *openai.ChatCompletionResponse, w io.Writer) error {
	if resp == nil || len(resp.Choices) == 0 {
		fmt.Fprintf(w, "data: [DONE]\n\n")
		return nil
	}
	chatID := resp.ID
	if len(chatID) > 8 {
		chatID = chatID[8:] // strip "chatcmpl-"
	}
	created := resp.Created
	if created == 0 {
		created = time.Now().Unix()
	}
	choice := resp.Choices[0]

	if len(choice.Message.ToolCalls) > 0 {
		chunks := monica.BuildToolCallsStreamChunks(model, chatID, created, choice.Message.ToolCalls)
		for _, chunk := range chunks {
			if _, err := fmt.Fprint(w, chunk); err != nil {
				return err
			}
		}
		return nil
	}

	content := choice.Message.Content
	chunk := fmt.Sprintf(`data: {"id":"chatcmpl-%s","object":"chat.completion.chunk","created":%d,"model":"%s","choices":[{"index":0,"delta":{"role":"assistant","content":%q},"finish_reason":null}]}`,
		chatID, created, model, content)
	fmt.Fprintf(w, "%s\n\n", chunk)
	finish := fmt.Sprintf(`data: {"id":"chatcmpl-%s","object":"chat.completion.chunk","created":%d,"model":"%s","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}`,
		chatID, created, model)
	fmt.Fprintf(w, "%s\n\n", finish)
	fmt.Fprintf(w, "data: [DONE]\n\n")
	return nil
}

// responseToSSEReader 将 ChatCompletionResponse 转为 SSE 格式的 io.Reader
func responseToSSEReader(model string, resp *openai.ChatCompletionResponse) io.Reader {
	var buf bytes.Buffer
	if err := writeResponseAsSSE(model, resp, &buf); err != nil {
		logger.Error("构建SSE失败", zap.Error(err))
	}
	return &buf
}
