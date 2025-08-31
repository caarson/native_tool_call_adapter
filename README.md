# NativeToolCallAdapter

## Overview

- BEFORE (without this app)
```mermaid
flowchart LR
    A[cline, Roo-Code] --> |XML tool defs|C[LLM]
    C -.-> |XML tool calls
    <u>with a potentially incorrect signature</u>|A
```

- AFTER (with this app)
```mermaid
flowchart LR
    A[cline, Roo-Code] --> |XML tool defs|B[**This app**]
    B --> |native tool defs|C[LLM]
    C -.-> |native tool calls
    <u>with an accurate signature</u>|B
    B -.-> |XML tool calls
    <u>with an accurate signature</u>|A
```


With relatively small models, [cline](https://github.com/cline/cline) and [Roo-Code](https://github.com/RooCodeInc/Roo-Code) tool calls may not be handled properly.
This application parses XML-formatted tool calls from Cline and Roo-Code and converts them into a format compliant with OpenAI API's tool_calls.

Significant improvements in performance have been confirmed with [gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b) and other models.

��r�I�����ȃ��f���ł́A[cline](https://github.com/cline/cline)��[Roo-Code](https://github.com/RooCodeInc/Roo-Code)�̃c�[���Ăяo���̏�������肭�����Ȃ����Ƃ�����܂��B
���̃A�v���P�[�V������Cline��Roo-Code��XML�`���̃c�[���Ăяo�����p�[�X���AOpenAI API��tool_calls�ɏ������`���ɕϊ����܂��B

[gpt-oss-20b](https://huggingface.co/openai/gpt-oss-20b)�Ȃǂŋ������啝�ɉ��P���邱�Ƃ��m�F�ł��Ă��܂��B

## Notes
This is an experimental application.
Parsing depends on the content of Cline/Roo-Code prompts, so it may stop working if the prompt specifications change in the future.

�����܂ł������I�ȃA�v���P�[�V�����ł��B
�p�[�X������Cline/Roo-Code�̃v�����v�g�̓��e�Ɉˑ����Ă��邽�߁A�����I�ȃv�����v�g�̎d�l�ύX�œ����Ȃ��Ȃ�\��������܂��B


## Execution Steps

1. `git clone https://github.com/irreg/native_tool_call_adapter.git
2. `uv sync`
3. `set TARGET_BASE_URL=actual LLM operating URL`  
   Example:
   - TARGET_BASE_URL: http://localhost:8080/v1
4. `uv run main.py`
5. The server will start on port 8000, so configure Cline and Roo-Code.  
   Example:
   - API Provider: OpenAI Compatible
   - Base URL: http://localhost:8000/v1
   - API Key: Setting the API key will automatically use it when communicating with TARGET_BASE_URL.

## ���s�菇
1. `git clone https://github.com/irreg/native_tool_call_adapter.git
2. `uv sync`
3. `set TARGET_BASE_URL=���ۂ�LLM�����삵�Ă���URL`  
   ��:
   - TARGET_BASE_URL: http://localhost:8080/v1
4. `uv run main.py`
5. port 8000�ŃT�[�o�[���N������̂ŁACline, Roo-Code��ݒ肵�Ă��������B  
   ��: 
   - API �v���o�C�_�[: OpenAI Compatible
   - Base URL: http://localhost:8000/v1
   - API�L�[: API�L�[��ݒ肷��ƁATARGET_BASE_URL�ƒʐM����Ƃ��Ɏ����I�Ɏg�p���܂��B


## Settings
The following settings can be configured as environment variables
TARGET_BASE_URL: (default: https://api.openai.com/v1) URL hosting the LLM
TOOL_CALL_ADAPTER_HOST: (default: 0.0.0.0) URL hosting this application
TOOL_CALL_ADAPTER_PORT: (default: 8000) Port hosting this application

���L�̐ݒ�����ϐ��Ƃ��Đݒ�\�ł�
TARGET_BASE_URL: (default: https://api.openai.com/v1) LLM���z�X�e�B���O���Ă���URL
TOOL_CALL_ADAPTER_HOST: (default: 0.0.0.0) ���̃A�v�����z�X�g����URL
TOOL_CALL_ADAPTER_PORT: (default: 8000) ���̃A�v�����z�X�g����|�[�g
