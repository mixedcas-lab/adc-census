# 랩 서버 최초 설정 절차 (Claude Code용)

이 문서는 랩 서버에서 실행 중인 Claude Code가 순서대로 수행하는 절차다. 먼저 저장소 루트의 CLAUDE.md 규칙을 읽는다. **[사용자 확인]** 표시가 있는 단계에서는 멈추고, 사용자가 할 일을 정확한 명령이나 클릭 경로로 알려준 뒤 완료 답을 기다린다.

저장소 위치는 `~/adc-census`로 가정한다. 다른 곳이면 아래 경로를 바꿔 쓴다.

## 1. 환경 점검

다음을 확인하고 결과를 표로 기록한다. 이 단계에서는 아무것도 설치하지 않는다.

- `python3 --version` (3.8 이상), `git --version`, `command -v python3`
- `crontab -l`이 동작하는지. 동작하지 않으면 `systemctl --user` 사용 가능 여부도 확인한다.
- IEEE API 접속: `curl -sS -o /dev/null -w '%{http_code}\n' https://ieeexploreapi.ieee.org/api/v1/search/articles` (키 없이 호출하므로 4xx여도 접속 자체는 성공)
- GitHub SSH: `ssh -o BatchMode=yes -o ConnectTimeout=8 -T git@github.com`. "Permission denied (publickey)"이면 22번 포트는 열려 있다. 시간 초과면 `ssh -o BatchMode=yes -o ConnectTimeout=8 -p 443 -T git@ssh.github.com`을 시도하고, 그쪽이 되면 3단계에서 443 포트 설정을 쓴다.
- 프록시가 필요한 환경이면(`env | grep -i _proxy`) 그 값이 cron에서도 필요하다는 점을 메모한다. 값 자체는 출력해도 되지만 비밀번호가 들어 있으면 가린다.

## 2. 저장소 받기

`~/adc-census`가 없으면 HTTPS로 클론한다(공개 저장소라 인증 불필요).

```bash
git clone https://github.com/mixedcas-lab/adc-census.git ~/adc-census
cd ~/adc-census
python3 -m unittest discover -s collector
```

테스트가 실패하면 원인을 고치기 전에 사용자에게 보고한다.

## 3. push용 deploy key

```bash
test -f ~/.ssh/adc_census || ssh-keygen -t ed25519 -f ~/.ssh/adc_census -N "" -C "adc-census@$(hostname)"
cat ~/.ssh/adc_census.pub
```

`gh auth status`가 성공하고 해당 계정이 저장소 관리자라면 다음으로 직접 등록해도 된다.

```bash
gh repo deploy-key add ~/.ssh/adc_census.pub --allow-write -R mixedcas-lab/adc-census -t "lab-server $(hostname)"
```

그렇지 않으면 **[사용자 확인]**: 공개키 한 줄을 보여주고 다음을 요청한다. GitHub 저장소 mixedcas-lab/adc-census → Settings → Deploy keys → Add deploy key에서 Title을 `lab-server`로 하고, 공개키를 붙여넣고, **Allow write access**를 체크한 뒤 Add key를 누른다.

등록 후 SSH 설정과 remote를 바꾼다. 1단계에서 22번 포트가 막혀 있었다면 `HostName ssh.github.com`과 `Port 443`을 쓴다.

```bash
grep -q "Host github-adc-census" ~/.ssh/config 2>/dev/null || cat >> ~/.ssh/config <<'EOF'

Host github-adc-census
  HostName github.com
  User git
  IdentityFile ~/.ssh/adc_census
  IdentitiesOnly yes
EOF
chmod 600 ~/.ssh/config
cd ~/adc-census
git remote set-url origin github-adc-census:mixedcas-lab/adc-census.git
git config user.name  "<사용자가 지정한 이름>"
git config user.email "<사용자가 지정한 메일>"
git fetch origin && git push --dry-run origin main
```

`--dry-run`이 권한 오류 없이 끝나야 다음 단계로 간다.

## 4. IEEE API 키

**[사용자 확인]**: 키를 채팅으로 받지 않는다. 사용자에게 **별도 터미널**에서 아래 명령을 직접 실행하라고 안내한다(입력 내용은 화면에 표시되지 않는다).

```bash
mkdir -p ~/.config/adc-census && read -rs -p "IEEE API key: " k && printf 'IEEE_API_KEY=%s\n' "$k" > ~/.config/adc-census/env && chmod 600 ~/.config/adc-census/env && unset k && echo saved
```

완료 답을 받으면 내용은 보지 않고 확인만 한다.

```bash
test -s ~/.config/adc-census/env && stat -c %a ~/.config/adc-census/env    # 600 이어야 함
```

## 5. API 점검 (1회 호출)

```bash
cd ~/adc-census
set -a; . ~/.config/adc-census/env; set +a
python3 collector/collect.py --probe
```

- `total_records`가 0보다 크고 abstract, index_terms, insert_date, authors, affiliation이 present인지 본다.
- 403 "Developer Inactive"나 인증 오류면 키가 아직 활성화되지 않은 것이다(발급 직후 수십 분 걸릴 수 있음). 사용자에게 알리고 멈춘다.
- 정렬·파라미터 관련 400 오류면 `collector/collect.py`의 요청 파라미터를 고치고 테스트를 통과시킨 뒤 다시 probe한다.

## 6. 소규모 시험 수집과 분류 점검

```bash
python3 collector/collect.py --max-calls 25
python3 collector/collect.py --report
```

`--report` 출력에서 다음을 점검하고, 문제가 있으면 고친다.

- **DROPPED publication title**: 대상 학회·저널인데 DROPPED로 나오면 `collector/venues.json`의 `venues[].match` 정규식을 고친다. 대상이 아닌 출판물(예: VLSI Technology 세션이 아닌 다른 심포지엄)이 섞여 들어오면 정상이다.
- **0건 task**: 질의가 틀린 것이다. `queries`의 `params`/`fallback`을 고친다.
- **랜덤 샘플**: ADC가 아닌 논문이 섞였거나 아키텍처 태그가 틀리면 `collector/classify.py`의 규칙을 고친다.
- **놓친 후보 목록**: 실제 ADC/DAC 논문이 보이면 relevance 규칙을 보강한다.

수정할 때마다 테스트를 추가하고 `python3 collector/collect.py --reclassify` → `--report`로 다시 확인한다(API 호출 없음). 수정이 끝나면 커밋하고 push한다.

```bash
python3 -m unittest discover -s collector && git add collector && git commit -m "collector: <무엇을 고쳤는지>" && git push origin main
```

## 7. 초기 수집 실행

```bash
mkdir -p ~/adc-census/logs
~/adc-census/scripts/update.sh 2>&1 | tee -a ~/adc-census/logs/update.log
python3 collector/collect.py --status
python3 collector/collect.py --report
```

전체 venue를 2023년부터 받는 데 대략 100회 안팎의 호출이 든다. 한도에 걸려 멈추면(종료 메시지 "stopped: ...") 정상이며 내일 cron이 이어받는다. push가 되었는지 `git log -1 --oneline`과 `git status`로 확인한다.

## 8. cron 등록

cron은 PATH가 최소한이므로 python3 경로를 확인해 넣는다.

```bash
PY=$(command -v python3); echo "$PY"
```

먼저 cron과 비슷한 최소 환경에서 동작하는지 시험한다.

```bash
env -i HOME="$HOME" PATH=/usr/bin:/bin PYTHON="$PY" bash ~/adc-census/scripts/update.sh
```

문제없으면 기존 crontab을 백업하고, 같은 줄이 없을 때만 추가한다. 1단계에서 프록시가 필요했다면 그 변수도 같은 줄에 넣는다.

```bash
crontab -l > ~/adc-census/logs/crontab.backup 2>/dev/null || true
LINE="17 6 * * * PYTHON=$PY $HOME/adc-census/scripts/update.sh >> $HOME/adc-census/logs/update.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'adc-census/scripts/update.sh'; echo "$LINE" ) | crontab -
crontab -l | grep adc-census
```

crontab을 쓸 수 없는 서버면 systemd user timer로 같은 동작을 만들고, 그 방법을 보고에 적는다.

## 9. GitHub Pages

`gh auth status`가 되면 확인하고, 꺼져 있으면 켠다.

```bash
gh api repos/mixedcas-lab/adc-census/pages 2>/dev/null || gh api -X POST repos/mixedcas-lab/adc-census/pages -f "source[branch]=main" -f "source[path]=/"
```

`gh`를 쓸 수 없으면 **[사용자 확인]**: 저장소 Settings → Pages → Build and deployment에서 Source를 Deploy from a branch, Branch를 main / (root)로 저장해 달라고 안내한다.

## 10. 보고

마지막에 다음을 정리해 사용자에게 보고한다.

1. 환경 점검 결과 (Python 경로, 포트·프록시, cron 방식)
2. `--status` 결과와 venue×연도별 ADC/DAC 건수 표 (`--report`의 표)
3. 수치 추출 커버리지, 오분류로 보이는 사례와 처리 내용
4. 고친 코드와 커밋 목록 (`git log --oneline origin/main -10`)
5. 등록한 cron 줄과 다음 실행 시각
6. 남은 일 (초기 수집 잔여분, Pages 설정 등)
