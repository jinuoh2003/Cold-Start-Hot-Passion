awslocal lambda invoke \
    --function-name stress-test-baseline \
    --payload fileb:///home/ubuntu/Cold-Start-Hot-Passion/dummy_data/payload_100mb.json \
    --cli-binary-format raw-in-base64-out \
    response_baseline.json


