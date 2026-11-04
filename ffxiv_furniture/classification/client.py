"""OpenAI-compatible transport, with explicit discovery and bounded retries."""
import json
import time
import urllib.error
import urllib.request


class Client:
    def __init__(self, endpoint, model, timeout=180, enable_thinking=None, structured_output=False):
        self.endpoint = endpoint.rstrip('/')
        self.model = model
        self.timeout = timeout
        self.enable_thinking = enable_thinking
        self.structured_output = structured_output
        self.response_format = None

    def _request(self, suffix, payload=None):
        data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        request = urllib.request.Request(self.endpoint + suffix, data=data,
                                         headers={'Content-Type': 'application/json'})
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                    raise RuntimeError(f'HTTP {error.code}: {error.read().decode("utf-8", "replace")[:1000]}') from error
            except (urllib.error.URLError, TimeoutError):
                if attempt == 2:
                    raise
            time.sleep(2 ** attempt)

    def discover(self):
        result = self._request('/models')
        models = [row['id'] for row in result.get('data', [])]
        if self.model not in models:
            raise ValueError(f'Requested model {self.model!r} not available; models={models!r}')
        return models

    def chat(self, messages, max_tokens=4096):
        payload = {'model': self.model, 'messages': messages, 'temperature': 0,
                   'max_tokens': max_tokens, 'stream': False}
        if self.enable_thinking is not None:
            payload['chat_template_kwargs'] = {'enable_thinking': self.enable_thinking}
        if self.response_format is not None:
            payload['response_format'] = self.response_format
        return self._request('/chat/completions', payload)


def parse_response(raw):
    # reasoning_content is deliberately never treated as an answer.
    if not isinstance(raw, dict):
        raise ValueError('Response must be an object')
    try:
        message = raw['choices'][0]['message']
        content = message['content']
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError('Missing assistant content') from error
    if not isinstance(content, str) or not content.strip():
        raise ValueError('Missing answer content (reasoning alone is not JSON)')
    text = content.strip()
    if text.startswith('```'):
        lines = text.splitlines()
        if len(lines) < 3 or lines[-1].strip() != '```':
            raise ValueError('Unclosed JSON fence')
        text = '\n'.join(lines[1:-1])
    return json.loads(text)
