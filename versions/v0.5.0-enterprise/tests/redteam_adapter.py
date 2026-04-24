import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import asyncio
import os
import sys

# Ensure src/ is in PYTHONPATH
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src")))

from biopipe.core.config import Config
from biopipe.cli import _build_runtime

class LLMMockAdapterHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return
            
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8")
        
        try:
            data = json.loads(body)
            # OpenAI / Garak pass messages array. Extract the last user message.
            messages = data.get("messages", [])
            prompt = messages[-1]["content"] if messages else ""
            
            # Start Biopipe runtime logic
            # This allows Garak to attack our AgentLoop, checking if RAG/Safety layers hold up!
            config = Config.load()
            runtime = _build_runtime(config)
            
            # Note: We run it in the existing event loop
            result_text = asyncio.run(runtime.run(prompt))
            asyncio.run(runtime.shutdown())
            
            response = {
                "id": "chatcmpl-123",
                "object": "chat.completion",
                "created": 1677652288,
                "model": "biopipe-cli-agent",
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": result_text,
                    },
                    "finish_reason": "stop"
                }]
            }
            
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))
            
        except Exception as exc:
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(exc)}).encode("utf-8"))

def run_server(port=11435):
    server_address = ('127.0.0.1', port)
    httpd = HTTPServer(server_address, LLMMockAdapterHandler)
    print(f"RedTeam Bridge running on http://127.0.0.1:{port}/v1/chat/completions")
    print("Now you can run Garak or Agentic-Security against this endpoint!")
    print("Example: garak --model_type openai --model_name gpt-3 --request_timeout 60 --rest_endpoint http://127.0.0.1:11435/v1/chat/completions")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
