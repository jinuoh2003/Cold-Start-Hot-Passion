# 1. SHM 폴더로 이동
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)/shm_src"

# 2. 코드 압축
zip -r shm_function.zip . 

awslocal lambda delete-function --function-name stress-test-shm 2>/dev/null

# 3. SHM 람다 함수 생성
awslocal lambda create-function \
    --function-name stress-test-shm \
    --runtime python3.9 \
    --handler handler.hello_handler \
    --role arn:aws:iam::000000000000:role/lambda-ex \
    --zip-file fileb://shm_function.zip
