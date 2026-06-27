# Monica Proxy — multi-stage Go build
FROM golang:1.25-alpine AS builder
WORKDIR /build
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o monica-proxy main.go

FROM alpine:3.20
RUN apk add --no-cache ca-certificates
WORKDIR /app
COPY --from=builder /build/monica-proxy .
EXPOSE 8080
CMD ["./monica-proxy"]
