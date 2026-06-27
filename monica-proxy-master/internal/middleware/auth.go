package middleware

import (
	"fmt"
	"net/http"
	"os"
	"reflect"
	"strings"

	"github.com/labstack/echo/v4"
)

// 向后兼容旧调用名
func AuthMiddleware(cfg any) echo.MiddlewareFunc {
	return BearerAuth(cfg)
}

// BearerAuth兼容：Authorization / x-api-key / api-key
func BearerAuth(cfg any) echo.MiddlewareFunc {
	allowed := resolveAllowedTokens(cfg)

	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			req := c.Request()

			auth := strings.TrimSpace(req.Header.Get("Authorization"))
			xKey := strings.TrimSpace(req.Header.Get("x-api-key"))
			if xKey == "" {
				xKey = strings.TrimSpace(req.Header.Get("X-API-Key"))
			}
			apiKey := strings.TrimSpace(req.Header.Get("api-key"))
			if apiKey == "" {
				apiKey = strings.TrimSpace(req.Header.Get("Api-Key"))
			}

			candidates := make([]string, 0, 3)
			if auth != "" {
				if strings.HasPrefix(strings.ToLower(auth), "bearer ") {
					candidates = append(candidates, strings.TrimSpace(auth[7:]))
				} else {
					candidates = append(candidates, auth)
				}
			}
			if xKey != "" {
				candidates = append(candidates, xKey)
			}
			if apiKey != "" {
				candidates = append(candidates, apiKey)
			}

			if len(candidates) == 0 {
				return echo.NewHTTPError(http.StatusUnauthorized, "invalid authorization header")
			}

			// 有明确 token 列表时做严格校验
			if len(allowed) > 0 {
				for _, t := range candidates {
					if _, ok := allowed[t]; ok {
						return next(c)
					}
				}
				return echo.NewHTTPError(http.StatusUnauthorized, "invalid authorization header")
			}

			// 未解析到配置 token 时，放行任意非空密钥（本地联调兜底）
			return next(c)
		}
	}
}

func resolveAllowedTokens(cfg any) map[string]struct{} {
	out := map[string]struct{}{}

	collectTokens(reflect.ValueOf(cfg), 0, out)

	for _, k := range []string{"BEARER_TOKEN", "AUTH_TOKEN", "API_KEY"} {
		v := strings.TrimSpace(os.Getenv(k))
		if v != "" {
			out[v] = struct{}{}
		}
	}

	return out
}

func collectTokens(v reflect.Value, depth int, out map[string]struct{}) {
	if !v.IsValid() || depth > 6 {
		return
	}

	if v.Kind() == reflect.Interface || v.Kind() == reflect.Ptr {
		if v.IsNil() {
			return
		}
		collectTokens(v.Elem(), depth+1, out)
		return
	}

	switch v.Kind() {
	case reflect.Struct:
		t := v.Type()
		for i := 0; i < v.NumField(); i++ {
			fv := v.Field(i)
			sf := t.Field(i)
			name := strings.ToLower(sf.Name)
			tag := strings.ToLower(string(sf.Tag))
			isTokenLike := strings.Contains(name, "token") || strings.Contains(name, "bearer") || strings.Contains(name, "api") || strings.Contains(name, "auth") || strings.Contains(tag, "token") || strings.Contains(tag, "api") || strings.Contains(tag, "auth")

			if fv.Kind() == reflect.String && isTokenLike {
				s := strings.TrimSpace(fv.String())
				if isUsableToken(s) {
					out[s] = struct{}{}
				}
			}

			collectTokens(fv, depth+1, out)
		}
	case reflect.Map:
		iter := v.MapRange()
		for iter.Next() {
			k := strings.ToLower(strings.TrimSpace(fmt.Sprint(iter.Key().Interface())))
			val := strings.TrimSpace(fmt.Sprint(iter.Value().Interface()))
			if (strings.Contains(k, "token") || strings.Contains(k, "api") || strings.Contains(k, "auth") || strings.Contains(k, "bearer")) && isUsableToken(val) {
				out[val] = struct{}{}
			}
			collectTokens(iter.Value(), depth+1, out)
		}
	case reflect.Slice, reflect.Array:
		for i := 0; i < v.Len(); i++ {
			collectTokens(v.Index(i), depth+1, out)
		}
	}
}

func isUsableToken(s string) bool {
	s = strings.TrimSpace(s)
	if s == "" {
		return false
	}
	ls := strings.ToLower(s)
	if ls == "your_token_here" || ls == "changeme" || ls == "replace_me" || ls == "xxx" {
		return false
	}
	return true
}
