# Gemini API Monitoring Discord Bot

독립 실행형 Discord 봇으로, 등록된 **Google API 키 × Gemini 모델** 조합에 가벼운
`countTokens` 신호를 보내 상태를 하나의 고정 Discord 임베드로 표시합니다.

## 주요 기능

- 키/모델 개수 하드코딩 없이 SQLite의 동적 매트릭스를 사용합니다.
- `200=🟢 ok`, `429=🔴 limited`, `401/403/404=⚠️ invalid`, 그 외 오류는 `⚪ unknown`으로 표시합니다.
- 설정에 저장하는 `google/<model>` 표시명은 API 호출 전에 `google/`을 제거합니다.
- 429의 `QuotaFailure`와 `RetryInfo.retryDelay`를 저장하고, 만료 후에도 실제 재검사 전에는 정상으로 추정하지 않습니다.
- 자동 검사와 `/refresh`는 설정된 stagger 간격으로 순차 호출합니다.
- API 키 원문 중복과 키 ID 중복을 모두 거부합니다. 키 값은 Fernet으로 암호화해 SQLite에 저장합니다.
- `/key`·`/model`·`/refresh` 명령은 관리자만 쓸 수 있고, 키 관련 응답은 ephemeral입니다.
- Discord 메시지는 렌더 결과가 바뀔 때만 edit합니다.

## 설치 및 실행

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
export KEY_ENCRYPTION_SECRET='위에서_생성한_키'
export DISCORD_BOT_TOKEN='Discord_봇_토큰'
python main.py
```

`config.yaml`의 `discord.channel_id`와 `security.admin_user_ids`는 운영 Discord 서버 값으로 바꾸어야 합니다.
`monitor.db`는 API 키(암호화됨), 상태, 등록 모델 및 상태 메시지 ID를 보관하므로 백업과 파일 권한을 관리해야 합니다.

## Ubuntu 서버 설치 및 systemd 실행

아래 예시는 Ubuntu 22.04/24.04에서 전용 시스템 사용자로 서비스를 실행하는 방식입니다.
프로젝트를 `/opt/gemini-api-monitoring-discord-bot`에 배치했다고 가정합니다.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
sudo useradd --system --create-home --shell /usr/sbin/nologin gemini-monitor
sudo mkdir -p /opt/gemini-api-monitoring-discord-bot /etc/gemini-api-monitor /var/lib/gemini-api-monitor

# 저장소 파일을 /opt/gemini-api-monitoring-discord-bot에 복사 또는 clone한 후 실행합니다.
sudo chown -R gemini-monitor:gemini-monitor /opt/gemini-api-monitoring-discord-bot /var/lib/gemini-api-monitor
cd /opt/gemini-api-monitoring-discord-bot
sudo -u gemini-monitor python3 -m venv .venv
sudo -u gemini-monitor .venv/bin/pip install -r requirements.txt

sudo cp config.example.yaml /etc/gemini-api-monitor/config.yaml
sudo chown root:gemini-monitor /etc/gemini-api-monitor/config.yaml
sudo chmod 640 /etc/gemini-api-monitor/config.yaml
```

`/etc/gemini-api-monitor/config.yaml`에서 `discord.channel_id`와
`security.admin_user_ids`를 실제 Discord 값으로 바꿉니다. 토큰과 암호화 키는
설정 파일에 쓰지 말고 별도의 root 전용 환경 파일에 저장합니다.

```bash
sudo sh -c 'cat > /etc/gemini-api-monitor/secrets.env <<EOF
DISCORD_BOT_TOKEN=Discord_봇_토큰
KEY_ENCRYPTION_SECRET=Fernet_암호화_키
EOF'
sudo chown root:gemini-monitor /etc/gemini-api-monitor/secrets.env
sudo chmod 640 /etc/gemini-api-monitor/secrets.env
```

Fernet 키는 다음 명령으로 생성합니다.

```bash
/opt/gemini-api-monitoring-discord-bot/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

제공된 systemd unit을 설치하고 서비스를 시작합니다.

```bash
sudo cp deploy/gemini-api-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gemini-api-monitor
sudo systemctl status gemini-api-monitor
sudo journalctl -u gemini-api-monitor -f
```

서비스는 상태 DB를 `/var/lib/gemini-api-monitor/monitor.db`에 저장합니다. 업데이트 후에는
`sudo systemctl restart gemini-api-monitor`을 실행합니다. `KEY_ENCRYPTION_SECRET`을 바꾸면
기존 DB의 API 키를 복호화할 수 없으므로 바꾸지 마십시오.

## Discord 명령어

```text
/key add id:<식별자> value:<Google API 키>
/key remove id:<식별자>
/key list
/model add name:google/gemini-3.6-flash
/model remove name:google/gemini-3.6-flash
/model list
/refresh
```

`/refresh`는 전체 조합의 검사를 즉시 시작하지만 API 호출은 `probe_stagger_sec` 간격으로 순차 실행합니다.
