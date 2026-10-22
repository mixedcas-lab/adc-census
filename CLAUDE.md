# ADC Census — Claude Code 작업 지침

ISSCC·VLSI·JSSC·CICC·ESSCIRC/ESSERC·A-SSCC·SSC-L·TCAS-I/II·TVLSI·IEEE Access의 ADC/DAC 논문을 IEEE Xplore API로 모아 GitHub Pages(https://mixedcas-lab.github.io/adc-census/)에 공개하는 저장소다. 랩 서버의 cron이 `scripts/update.sh`로 매달 갱신한다. 구조와 데이터 필드는 README.md를 본다. 서버 최초 설정은 docs/server-setup.md를 따른다.

## 반드시 지킬 것

- **API 키**: `~/.config/adc-census/env`(`IEEE_API_KEY=...`)에만 둔다. 키를 출력하거나(cat, echo, env, set -x 금지), 사용자에게 채팅으로 요청하거나, 저장소에 쓰지 않는다. 파일 확인은 `test -s` 와 `stat -c %a`로만 한다.
- **cache/는 커밋 금지**: IEEE 원본 응답(초록 포함)이다. 공개 데이터(`data/papers.json`)에도 초록을 넣지 않는다.
- **API 한도**: 표준 키는 하루 약 200회다. 디버깅할 때는 `--probe`(1회)나 `--max-calls 10`처럼 작게 쓰고, 분류 규칙은 `--reclassify`로 캐시에서 다시 돌린다(API 호출 없음). 오늘 한도를 다 쓰면 cron이 내일 이어받는다.
- **공용 서버**: sudo, 시스템 패키지 설치, 다른 사용자의 crontab이나 파일 수정은 하지 않는다. 표준 라이브러리만 쓴다.
- **코드 수정**: `collector/`를 고치면 `collector/test_collector.py`에 해당 사례를 테스트로 추가하고 `python3 -m unittest discover -s collector`가 통과해야 커밋한다. `data/*.json`은 직접 편집하지 않는다(수집기가 생성). `data/annotations.csv`는 학생 검수용이며 사람의 편집을 덮어쓰지 않는다.
- **커밋**: main에 직접 커밋한다. 메시지는 `collector: ...`, `site: ...`, `data: ...`처럼 영역을 앞에 붙인다.

## 자주 쓰는 명령

```bash
python3 -m unittest discover -s collector   # 오프라인 테스트
python3 collector/collect.py --probe        # 키·네트워크·응답 필드 확인 (API 1회)
python3 collector/collect.py --status       # 초기 수집 진행 상황
python3 collector/collect.py --report       # venue 매칭·분류·수치 추출 점검 (API 없음)
python3 collector/collect.py --reclassify   # 규칙 수정 후 캐시에서 재분류 (API 없음)
scripts/update.sh                           # 수집 → 커밋 → push (cron이 매일 실행)
tail -50 logs/update.log                    # cron 실행 기록
```

`collect.py` 종료 코드: 0 정상, 2 키 없음, 3 오늘 API 한도 소진(진행 상황 저장됨, 정상), 그 외 오류.

## 갱신이 실패했을 때 점검 순서

1. `tail -80 logs/update.log`로 오류를 확인한다.
2. `git status`, `git log -3 --oneline`, `git pull --rebase`로 push 충돌 여부를 본다.
3. `python3 collector/collect.py --probe`로 키·네트워크를 확인한다. 403 "Over Rate"는 한도, 그 외 403은 키 문제다.
4. 특정 venue가 0건이면 `--report`의 "returned 0 records" 목록을 보고 `collector/venues.json`의 질의를 고친다. `data/state.json`의 `variant`가 그 venue를 fallback으로 바꿔 두었는지도 확인한다.
