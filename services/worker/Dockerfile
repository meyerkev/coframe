FROM golang:1.23-alpine AS build

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o /bin/worker ./cmd/worker

FROM alpine:3.21
WORKDIR /app
COPY --from=build /bin/worker /app/worker
EXPOSE 9101
CMD ["/app/worker"]
