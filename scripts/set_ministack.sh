#!/bin/bash

# 1. 기본 환경 변수 설정
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
ALIAS_AWS="aws --endpoint-url=http://localhost:4566"

echo "[*] Initializing LocalStack Resources..."

# 1. 기존에 떠 있는 모든 stress-test 관련 함수 삭제 (청소)
awslocal lambda delete-function --function-name stress-test-shm 2>/dev/null
awslocal lambda delete-function --function-name stress-test-shm-container 2>/dev/null

# 2. 함수 생성 (이름 딱 하나로 고정: stress-test-shm)
awslocal lambda create-function \
    --function-name stress-test-shm \
    --package-type Image \
    --code ImageUri=my-shm-lambda:latest \
    --role arn:aws:iam::000000000000:role/lambda-ex \
    --memory-size 1024 \
    --timeout 30

# 3. S3 권한 부여 (이게 빠지면 400 에러 납니다)
awslocal lambda add-permission \
    --function-name stress-test-shm \
    --statement-id s3-cross-account \
    --action "lambda:InvokeFunction" \
    --principal s3.amazonaws.com \
    --source-arn arn:aws:s3:::my-bucket

# 4. S3 -> Lambda 트리거 연결 (핵심!)
# S3 버킷에 파일이 생성(Put)될 때 람다를 호출하도록 설정합니다.
echo "[*] Configuring S3 Event Trigger..."
awslocal lambda add-permission \
    --function-name stress-test-shm \
    --statement-id s3-trigger \
    --action "lambda:InvokeFunction" \
    --principal s3.amazonaws.com \
    --source-arn arn:aws:s3:::my-bucket

$ALIAS_AWS s3api put-bucket-notification-configuration \
    --bucket my-bucket \
    --notification-configuration '{
        "LambdaFunctionConfigurations": [
            {
                "LambdaFunctionArn": "arn:aws:lambda:us-east-1:000000000000:function:stress-test-shm",
                "Events": ["s3:ObjectCreated:*"]
            }
        ]
    }'

echo "[*] Setup Complete! Testing Resources..."
awslocal s3 ls
awslocal lambda list-functions --query "Functions[].FunctionName"
