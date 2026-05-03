# Docker 배포

라즈베리파이에서 `gaon-climate-edge`를 컨테이너로 실행하기 위한 Docker 구성입니다.

## 파일

- `Dockerfile`: Python 런타임과 DHT22/GPIO 관련 의존성을 포함한 이미지 정의
- `compose.yml`: 라즈베리파이 GPIO 장치 접근 권한과 재시작 정책을 포함한 실행 구성

## 빠른 실행

`prod` 모드로 실행할 예정이라면 프로젝트 루트에서 환경 파일을 준비합니다.

```bash
cp config/.env.example config/.env
```

`config/.env`와 `config/config.yml`을 라즈베리파이 환경에 맞게 수정한 뒤 실행합니다.
`local` 모드는 `config/.env`가 없어도 실행할 수 있습니다.

```bash
docker compose -f docker/compose.yml up -d --build
```

기본값은 `local` 모드입니다. 운영 서버로 전송하려면 `docker/compose.yml`의 `command`를 아래처럼 바꿉니다.

```yaml
command: ["--mode", "prod"]
```

로그는 아래 명령으로 확인합니다.

```bash
docker compose -f docker/compose.yml logs -f
```

중지하려면 아래 명령을 실행합니다.

```bash
docker compose -f docker/compose.yml down
```
