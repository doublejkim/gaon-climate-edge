# Docker 배포

라즈베리파이에서 `gaon-climate-edge`를 컨테이너로 실행하기 위한 Docker 구성입니다.

## 파일

- `Dockerfile`: Python 런타임과 DHT22/GPIO 관련 의존성을 포함한 이미지 정의
- `compose.yml`: 라즈베리파이 GPIO 장치 접근 권한과 재시작 정책을 포함한 실행 구성
- `deploy.sh`: 라즈베리파이에서 git clone/pull, Docker 빌드, 컨테이너 실행까지 처리하는 배포 스크립트

## 스크립트 배포

라즈베리파이에서 처음 배포할 때는 아래 명령을 실행합니다.
기본 설치 경로는 `$HOME/gaon-climate-edge`입니다.

```bash
curl -fsSL https://raw.githubusercontent.com/doublejkim/gaon-climate-edge/main/docker/deploy.sh -o /tmp/gaon-climate-deploy.sh
chmod +x /tmp/gaon-climate-deploy.sh
/tmp/gaon-climate-deploy.sh local
```

이미 `$HOME/gaon-climate-edge`가 있으면 스크립트가 `git pull --ff-only`로 갱신한 뒤 Docker 이미지를 다시 빌드하고 컨테이너를 재시작합니다.

설치 경로 또는 브랜치를 바꾸려면 환경변수를 지정합니다.

```bash
APP_DIR=/opt/gaon-climate-edge BRANCH=main /tmp/gaon-climate-deploy.sh local
```

### local 환경

센서 연결과 로그 확인용 환경입니다.
서버로 데이터를 전송하지 않으며 `config/.env`가 없어도 실행할 수 있습니다.

```bash
/tmp/gaon-climate-deploy.sh local
```

로그를 확인합니다.

```bash
cd ~/gaon-climate-edge
CLIMATE_MODE=local docker compose -f docker/compose.yml logs -f
```

### prod 환경

운영 서버로 데이터를 전송하는 환경입니다.
먼저 저장소를 받은 뒤 환경 파일을 준비합니다.

```bash
/tmp/gaon-climate-deploy.sh local
cd ~/gaon-climate-edge
cp config/.env.example config/.env
```

`config/.env`에 실제 서버 주소와 인증키를 설정합니다.

```bash
CLIMATE_SERVER_URL=https://example.com
CLIMATE_API_KEY=
REQUEST_TIMEOUT_SECONDS=10
```

그 다음 prod 모드로 배포합니다.

```bash
/tmp/gaon-climate-deploy.sh prod
```

prod 로그를 확인합니다.

```bash
cd ~/gaon-climate-edge
CLIMATE_MODE=prod docker compose -f docker/compose.yml logs -f
```

## 수동 실행

`prod` 모드로 실행할 예정이라면 프로젝트 루트에서 환경 파일을 준비합니다.

```bash
cp config/.env.example config/.env
```

`config/.env`와 `config/config.yml`을 라즈베리파이 환경에 맞게 수정한 뒤 실행합니다.
`local` 모드는 `config/.env`가 없어도 실행할 수 있습니다.

```bash
docker compose -f docker/compose.yml up -d --build
```

기본값은 `local` 모드입니다. 운영 서버로 전송하려면 `CLIMATE_MODE=prod`를 함께 지정합니다.

```bash
CLIMATE_MODE=prod docker compose -f docker/compose.yml up -d --build
```

로그는 아래 명령으로 확인합니다.

```bash
docker compose -f docker/compose.yml logs -f
```

중지하려면 아래 명령을 실행합니다.

```bash
docker compose -f docker/compose.yml down
```
