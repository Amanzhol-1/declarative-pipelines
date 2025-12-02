### Имя контракта: CiPipeline

Этот ямл файл является основным, который описывает структуру генерируемого пайплайна, который потом обрабатывается экзекьютором

### Структуру/Дизайн

```
apiVersion: v1
kind: CiPipeline

pipeline:
  id: <pipeline_id>
  name: Pipeline
  vars:
    VAR1: var1
    ...
  stages:
    - name: stage for notification:
      job: send-email-notification
    - name: stage for report:
      job: send-report

  jobs:
    send-email-notification:
      path: ${DOCKER_IMAGE}
      command: cli_command
      input:
        params:
          email_address: address@gmail.com
        secure_params:
          password: ...
    when:
        statuses: SUCCESS
  
  jobs:
    send-report:
      path: ${DOCKER_IMAGE}
      command: cli_command
      input:
        params:
          send_report_to_email_address: address@gmail.com
        secure_params:
          password: ...
      output: 
        HTML_REPORT: report.html
        MD_REPORT: report.md
    when:
        statuses: SUCCESS
    

```

