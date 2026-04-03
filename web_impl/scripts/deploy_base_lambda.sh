# 1. Baseline 폴더로 이동
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)/baseline_src"

# 2. 코드 압축
rm -f baseline_function.zip
zip -r baseline_function.zip . 

# 기존 함수 삭제
awslocal lambda delete-function --function-name stress-test-baseline 2>/dev/null

# 3. Baseline 람다 함수 생성
awslocal lambda create-function \
    --function-name stress-test-baseline \
    --runtime python3.9 \
    --handler handler.hello_handler \
    --role arn:aws:iam::000000000000:role/lambda-ex \
    --zip-file fileb://baseline_function.zip
