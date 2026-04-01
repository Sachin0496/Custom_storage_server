import urllib.request, json
import email.message

boundary = '-----WebKitFormBoundary7MA4YWxkTrZu0gW'
token = 'testing123'

body = (
    f'--{boundary}\r\n'
    f'Content-Disposition: form-data; name="file"; filename="test.txt"\r\n'
    f'Content-Type: text/plain\r\n\r\n'
    f'Hello World\r\n'
    f'--{boundary}--\r\n'
).encode('utf-8')

req = urllib.request.Request(
    'http://localhost:8090/api/shares/3b0c7f46-0da9-469c-91dc-e7aa0be3ab2a/upload?path=&overwrite=false',
    data=body,
    headers={
        'Authorization': f'Bearer Pranesh:{token}',
        'Content-Type': f'multipart/form-data; boundary={boundary}',
        'Content-Length': str(len(body))
    },
    method='POST'
)

try:
    with urllib.request.urlopen(req) as response:
        print("Success:", response.read().decode())
except urllib.error.HTTPError as e:
    print("Error:", e.code, e.reason, e.read().decode())
