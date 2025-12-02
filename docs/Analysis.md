## Сравнительный анализ

Мы не нашли технологии, инструмента который бы реализовывал то, что мы хотим сделать, но есть что то около похожее, что стоит изучить, как у них это реализовано

### Dagger - portable devkit

https://www.reddit.com/r/devops/comments/tvrfvc/dagger_a_portable_devkit_for_cicd_pipelines/

звучит очень классно, но на деле пайплайн пишется примерно так
```
func Pipeline(ctx context.Context, client *dagger.Client) error {
    src := client.Host().Directory(".")
    return client.Container().
        From("golang:1.22").
        WithMountedDirectory("/src", src).
        WithWorkdir("/src").
        WithExec([]string{"go", "test", "./..."}).
        Sync(ctx)
}
```

Это вообще не то. Пайплайны смогут писать только девопсы, а не любой человек, как хотим сделать мы

И еще тут своя система, запускается через dagger run, а не в гитлабе, или дженкиксе как хотим мы

### Earthly

https://github.com/earthly/earthly#quick-start

Какой то фреймворк для пайплайнов, звучит опять неплохо, но на деле вообще не юзер френдли, просто громоский инструмент

```
VERSION 0.8
FROM golang:1.15-alpine3.13
WORKDIR /proto-example

proto:
  FROM namely/protoc-all:1.29_4
  COPY api.proto /defs
  RUN --entrypoint -- -f api.proto -l go
  SAVE ARTIFACT ./gen/pb-go /pb AS LOCAL pb

build:
  COPY go.mod go.sum .
  RUN go mod download
  COPY +proto/pb pb
  COPY main.go ./
  RUN go build -o build/proto-example main.go
  SAVE ARTIFACT build/proto-example
```
И пайплайны пишутся не понятно

### Other tools
Остальные инструменты еще более не понятны и вообще не про нас. Все хотят свою платформу с пайплайнами, а не интреграцию для гитлаба и дженкинса
