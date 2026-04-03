awslocal lambda invoke \
    --function-name stress-test-shm \
    --payload "fileb://$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)/dummy_data/payload_100mb.json" \
    --cli-binary-format raw-in-base64-out \
    response_shm.json
