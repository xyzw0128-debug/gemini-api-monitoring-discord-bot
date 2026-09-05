# Gemini API 한도 확인 Discord 봇

이 봇은 여러 개의 Google API 키와 Gemini 모델을 주기적으로 확인해서, **지금 어느 키와 모델을 쓸 수 있는지** Discord 채널에 한눈에 보여 줍니다.

봇은 Discord 채널에 메시지를 계속 여러 개 보내지 않습니다. 상태판 메시지 **하나만** 만들고, 상태가 바뀌었을 때만 그 메시지를 수정합니다.

예시 화면:

```text
Gemini 3.6 Flash   🟢🟢🔴
Gemini 3.5 Flash   🟢⚪🟢

🟢 사용 가능 · 🔴 한도 도달 · ⚠️ 키/모델 오류 · ⚪ 확인 중 또는 일시 오류
```

---

## 시작하기 전에 준비할 것

아래 네 가지가 필요합니다.

1. **Discord 봇 토큰**
2. 상태판을 올릴 **Discord 채널 ID**
3. 명령어를 사용할 본인의 **Discord 사용자 ID**
4. Google API 키 한 개 이상

Discord Developer Portal에서 봇을 서버에 초대할 때는 다음을 선택하세요.

- Scopes: `bot`, `applications.commands`
- Bot Permissions: `View Channel`, `Send Messages`, `Embed Links`, `Read Message History`

`Read Message History` 권한이 없으면, 봇이 예전에 만든 상태판 메시지를 찾아서 업데이트하지 못할 수 있습니다.

---

## 가장 쉬운 실행 방법: 내 PC에서 먼저 실행하기

아래 방법은 “일단 잘 되는지 확인”할 때 쓰세요.

### 0. 먼저 프로젝트 파일을 PC에 받아야 합니다

위 명령에서 오류가 난 이유는 현재 PC에 `gemini-api-monitoring-discord-bot` 폴더가 없기 때문입니다.
아래 설치 명령은 **프로젝트 파일을 이미 받은 다음**에만 실행할 수 있습니다.

GitHub에 저장소가 있다면, 저장소 주소를 넣어 아래처럼 받습니다.

```bash
cd ~
git clone <저장소_주소> gemini-api-monitoring-discord-bot
cd ~/gemini-api-monitoring-discord-bot
```

예를 들어 주소가 `https://github.com/내계정/내저장소.git`라면 다음과 같습니다.

```bash
git clone https://github.com/내계정/내저장소.git gemini-api-monitoring-discord-bot
```

GitHub을 사용하지 않는다면, 이 프로젝트 폴더 전체를 Ubuntu PC로 복사한 뒤 그 폴더에서 다음 단계로 진행하세요.

### 1. 필요한 프로그램 설치

Ubuntu라면 터미널에서 실행합니다.

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### 2. 프로젝트 폴더에서 준비

```bash
cd ~/gemini-api-monitoring-discord-bot
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp config.example.yaml config.yaml
```

### 3. `config.yaml` 수정

파일을 열고 아래 두 값을 본인의 값으로 바꾸세요.

```yaml
discord:
  channel_id: "상태판을_올릴_채널_ID"

security:
  admin_user_ids: ["내_Discord_사용자_ID"]
```

처음에는 `api_keys`를 직접 파일에 넣지 않아도 됩니다. 봇을 켠 뒤 Discord 명령어로 추가할 수 있습니다.

### 4. 비밀값 설정

먼저 API 키를 안전하게 저장하는 데 쓸 암호화 키를 만듭니다.

```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

출력된 값을 복사한 다음 아래처럼 입력합니다.

```bash
export KEY_ENCRYPTION_SECRET='방금_복사한_값'
export DISCORD_BOT_TOKEN='Discord_봇_토큰'
```

### 5. 봇 켜기

```bash
python main.py
```

Discord 채널에 빈 상태판 메시지가 나타나면 성공입니다.

### 6. Discord에서 키 등록하고 확인하기

Discord에서 다음 순서대로 실행합니다.

```text
/key add id:main value:Google_API_키
/refresh
```

`/refresh`가 끝나면 상태판에 아이콘이 표시됩니다. 모델은 기본으로 예시 모델 목록이 등록되지만, 필요하면 아래처럼 추가할 수 있습니다.

```text
/model add name:google/gemini-3.6-flash
/refresh
```

> API 키를 넣는 `/key add`의 응답은 본인에게만 보입니다. 그래도 API 키는 타인에게 공유하지 마세요.

---

## Ubuntu 서버에서 계속 켜 두기

서버를 재부팅해도 봇이 자동으로 다시 켜지게 하려면 아래 방법을 사용하세요.

이 설명은 Ubuntu 22.04와 24.04 기준입니다.

### 1. 서버에 프로젝트 올리기

프로젝트 전체를 서버의 아래 위치에 복사하거나 git clone하세요.

```text
/opt/gemini-api-monitoring-discord-bot
```

### 2. 한 번에 설치 명령 실행

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
sudo useradd --system --create-home --shell /usr/sbin/nologin gemini-monitor
sudo mkdir -p /etc/gemini-api-monitor /var/lib/gemini-api-monitor
sudo chown -R gemini-monitor:gemini-monitor /opt/gemini-api-monitoring-discord-bot /var/lib/gemini-api-monitor

cd /opt/gemini-api-monitoring-discord-bot
sudo -u gemini-monitor python3 -m venv .venv
sudo -u gemini-monitor .venv/bin/pip install -r requirements.txt
```

### 3. Discord 정보 설정

```bash
sudo cp /opt/gemini-api-monitoring-discord-bot/config.example.yaml /etc/gemini-api-monitor/config.yaml
sudo nano /etc/gemini-api-monitor/config.yaml
```

열린 파일에서 다음 두 값만 먼저 바꾸면 됩니다.

```yaml
discord:
  channel_id: "상태판을_올릴_채널_ID"

security:
  admin_user_ids: ["내_Discord_사용자_ID"]
```

저장 후 파일 권한을 제한합니다.

```bash
sudo chown root:gemini-monitor /etc/gemini-api-monitor/config.yaml
sudo chmod 640 /etc/gemini-api-monitor/config.yaml
```

### 4. 봇 토큰과 암호화 키 저장

암호화 키를 하나 만듭니다.

```bash
/opt/gemini-api-monitoring-discord-bot/.venv/bin/python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

그 값을 복사한 뒤 아래 명령을 실행합니다.

```bash
sudo nano /etc/gemini-api-monitor/secrets.env
```

파일에 아래 두 줄을 넣고, 오른쪽 값을 실제 값으로 바꾸세요.

```text
DISCORD_BOT_TOKEN=Discord_봇_토큰
KEY_ENCRYPTION_SECRET=방금_만든_암호화_키
```

저장 후 권한을 제한합니다.

```bash
sudo chown root:gemini-monitor /etc/gemini-api-monitor/secrets.env
sudo chmod 640 /etc/gemini-api-monitor/secrets.env
```

### 5. 자동 실행 켜기

```bash
sudo cp /opt/gemini-api-monitoring-discord-bot/deploy/gemini-api-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gemini-api-monitor
```

정상 실행 확인:

```bash
sudo systemctl status gemini-api-monitor
```

실시간 로그 보기:

```bash
sudo journalctl -u gemini-api-monitor -f
```

코드를 업데이트한 뒤에는 아래 명령으로 봇을 다시 시작합니다.

```bash
sudo systemctl restart gemini-api-monitor
```

> **중요:** `KEY_ENCRYPTION_SECRET`은 나중에 바꾸지 마세요. 바꾸면 기존에 저장한 Google API 키를 읽을 수 없습니다.

---

## v1.1: OpenClaw 실사용 오류도 함께 보기 (선택)

기본 봇은 각 API 키와 모델에 직접 신호를 보내 상태를 확인합니다. 여기에 OpenClaw 로그 감지를 켜면,
유이가 실제로 사용 중 429, 503, 과부하 또는 timeout을 만났을 때 해당 모델을 바로 다시 확인합니다.

이 기능은 **선택 사항**입니다. OpenClaw를 쓰지 않으면 아무것도 바꿀 필요가 없습니다.

같은 Ubuntu 서버에서 OpenClaw와 봇을 실행한다면 `/etc/gemini-api-monitor/config.yaml`에서 다음을 바꾸세요.

```yaml
openclaw_observer:
  enabled: true
```

그 뒤 봇을 다시 시작합니다.

```bash
sudo systemctl restart gemini-api-monitor
sudo journalctl -u gemini-api-monitor -f
```

상태판에는 최근 실사용 오류가 아래처럼 **보조 정보**로 표시됩니다.

```text
실사용 감지 (보조 정보)
• gemini-3.5-flash: OpenClaw overloaded 감지 — 재확인 요청됨
```

OpenClaw 로그만으로 “어느 API 키가 제한되었다”고 확정하지는 않습니다. 로그는 빠른 경고 역할만 하고,
최종 🟢/🔴 상태는 봇이 해당 키와 모델에 직접 보낸 확인 요청 결과로 결정됩니다.

> systemd 서비스는 `gemini-monitor` 사용자로 실행됩니다. `openclaw` 명령도 이 사용자가 실행할 수 있어야 합니다.
> `sudo -u gemini-monitor openclaw logs --follow`가 실패한다면 OpenClaw 설치 위치/권한을 먼저 확인하세요.

---

## Discord 명령어 모음

| 명령어 | 하는 일 |
| --- | --- |
| `/key add id:main value:API키` | API 키를 추가합니다. 같은 키는 중복 추가되지 않습니다. |
| `/key remove id:main` | API 키를 삭제합니다. |
| `/key list` | 등록된 키 이름만 보여 줍니다. 키 값은 보여 주지 않습니다. |
| `/model add name:google/gemini-3.6-flash` | 확인할 Gemini 모델을 추가합니다. |
| `/model remove name:google/gemini-3.6-flash` | 모델을 삭제합니다. |
| `/model list` | 등록된 모델 목록을 보여 줍니다. |
| `/refresh` | 모든 키와 모델을 지금 바로 다시 확인합니다. |

명령어는 `config.yaml`에 넣은 관리자만 사용할 수 있습니다.

---

## 아이콘 뜻

| 아이콘 | 뜻 | 보통 할 일 |
| --- | --- | --- |
| 🟢 | 지금 확인했을 때 사용 가능 | 그대로 사용 |
| 🔴 | Google이 429(한도 도달)를 반환 | 잠시 기다린 뒤 다시 확인 |
| ⚠️ | API 키, 권한 또는 모델 이름 문제 | 키와 모델 이름 확인 |
| ⚪ | 인터넷 오류, 일시적인 서버 오류, 또는 재확인 대기 | `/refresh`로 다시 확인 |

봇은 한도 해제 예정 시간이 지나더라도 바로 🟢으로 바꾸지 않습니다. 실제 Google 서버 확인이 성공해야만 🟢으로 표시합니다.

## 자주 묻는 질문

### 상태판이 안 보여요.

1. 봇이 해당 채널을 볼 수 있는지 확인하세요.
2. 봇에 `Send Messages`와 `Embed Links` 권한이 있는지 확인하세요.
3. `sudo journalctl -u gemini-api-monitor -f`로 오류를 확인하세요.

### `/key`나 `/refresh`가 안 보여요.

봇 초대 URL에 `applications.commands` scope가 있는지 확인하세요. Discord에서 명령어가 보이기까지 잠시 걸릴 수 있습니다.

### 키를 추가했는데 바로 🟢이 안 돼요.

키를 추가한 뒤 `/refresh`를 실행하세요. 봇은 API 요청을 한꺼번에 보내지 않기 때문에, 키와 모델 수가 많으면 결과가 순서대로 나타납니다.
