#!/bin/bash

cd /home/ubuntu/Cold-Start-Hot-Passion/dummy_data

BUCKET_NAME="demo-web-bucket"

echo "1. S3 버킷 생성 중 ($BUCKET_NAME)..."
awslocal s3 mb s3://$BUCKET_NAME 2>/dev/null

echo "2. 더미 데이터(10MB, 50MB, 100MB) 생성 중... (조금만 기다려주세요)"
dd if=/dev/urandom of=dummy_10mb.txt bs=1M count=10 status=none
dd if=/dev/urandom of=dummy_50mb.txt bs=1M count=50 status=none
dd if=/dev/urandom of=dummy_100mb.txt bs=1M count=100 status=none

echo "3. S3 버킷으로 파일 업로드 중..."
awslocal s3 cp dummy_10mb.txt s3://$BUCKET_NAME/dummy_10mb.txt
awslocal s3 cp dummy_50mb.txt s3://$BUCKET_NAME/dummy_50mb.txt
awslocal s3 cp dummy_100mb.txt s3://$BUCKET_NAME/dummy_100mb.txt

echo "4. 로컬에 남은 임시 더미 파일 삭제 중..."
rm dummy_10mb.txt dummy_50mb.txt dummy_100mb.txt

echo "5. 테스트 호출용 Payload JSON 파일 생성 중..."

echo "*** 모든 데이터 세팅 완료! 이제 10, 50, 100MB 페이로드로 테스트할 준비가 끝났습니다."
awslocal s3 ls s3://$BUCKET_NAME --human-readable
