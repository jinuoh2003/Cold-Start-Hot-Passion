# 1. ngrok 공식 저장소 키 추가
curl -s https://ngrok-agent.s3.amazonaws.com/ngrok.asc | sudo tee /etc/apt/keyrings/ngrok.asc >/dev/null

# 2. apt 소스 리스트에 ngrok 추가
echo "deb [signed-by=/etc/apt/keyrings/ngrok.asc] https://ngrok-agent.s3.amazonaws.com buster main" | sudo tee /etc/apt/sources.list.d/ngrok.list

# 3. 패키지 업데이트 및 설치 진행
sudo apt update
sudo apt install ngrok
