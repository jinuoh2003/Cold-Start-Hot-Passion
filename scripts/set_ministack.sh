#!/bin/bash

# 환경 변수 설정
export AWS_ACCESS_KEY_ID=test
export AWS_SECRET_ACCESS_KEY=test
export AWS_DEFAULT_REGION=us-east-1
ALIAS_AWS="aws --endpoint-url=http://localhost:4566"

echo "[*] Initializing LocalStack Resources..."

# 0. 기존에 떠 있는 모든 test 관련 함수 삭제
# awslocal lambda delete-function --function-name stress-test-lambda 2>/dev/null
# awslocal lambda delete-function --function-name stress-test-shm 2>/dev/null
# awslocal lambda delete-function --function-name stress-test-shm-container 2>/dev/null

# 1. 함수 생성
awslocal lambda create-function \
    --function-name stress-test-lambda \
    --package-type Image \
    --code ImageUri=my-lambda:latest \
    --role arn:aws:iam::000000000000:role/lambda-ex \
    --memory-size 1024 \
    --timeout 30

# 2. S3 권한 부여
awslocal lambda add-permission \
    --function-name stress-test-lambda \
    --statement-id s3-cross-account \
    --action "lambda:InvokeFunction" \
    --principal s3.amazonaws.com \
    --source-arn arn:aws:s3:::my-bucket

# 3. S3 -> Lambda 트리거 연결
# S3 버킷에 파일이 생성(Put)될 때 Lambda를 호출하도록 설정
echo "[*] Configuring S3 Event Trigger..."

awslocal lambda add-permission \
    --function-name stress-test-lambda \
    --statement-id s3-trigger \
    --action "lambda:InvokeFunction" \
    --principal s3.amazonaws.com \
    --source-arn arn:aws:s3:::my-bucket

$ALIAS_AWS s3api put-bucket-notification-configuration \
    --bucket my-bucket \
    --notification-configuration '{
        "LambdaFunctionConfigurations": [
            {
                "LambdaFunctionArn": "arn:aws:lambda:us-east-1:000000000000:function:stress-test-lambda",
                "Events": ["s3:ObjectCreated:*"]
            }
        ]
    }'

echo "[*] Setup Complete! Testing Resources..."
awslocal s3 ls
awslocal lambda list-functions --query "Functions[].FunctionName"
