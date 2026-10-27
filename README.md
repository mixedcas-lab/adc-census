<p>
  <a href="https://mcas.uos.ac.kr"><img src="assets/mcaslab.png" alt="MCAS Lab" height="34"></a>
  &nbsp;&nbsp;
  <a href="https://www.uos.ac.kr"><img src="assets/uos.png" alt="University of Seoul" height="20"></a>
</p>

# ADC Census

ISSCC, VLSI, JSSC, CICC, ESSCIRC/ESSERC, A-SSCC, SSC-L, TCAS-I/II, TVLSI, IEEE Access에 실린 ADC·DAC 논문을 매달 자동으로 모아 보여주는 사이트입니다. MCAS Lab(서울시립대학교 첨단융합학부)에서 운영합니다.

- 사이트: https://mixedcas-lab.github.io/adc-census/
- 데이터 출처: IEEE Xplore API (서지 메타데이터와 링크만 공개, 초록·본문은 올리지 않음)

## 구성

```
index.html, app.js, style.css   사이트 (빌드 과정 없음, GitHub Pages가 그대로 서비스)
data/papers.json                수집·분류된 논문 목록 (수집기가 생성)
data/meta.json                  갱신일, 범위, 집계
data/state.json                 수집 진행 상태 (초기 수집 이어하기, 마지막 갱신일)
data/annotations.csv            학생 검수 값 (사람이 편집)
collector/collect.py            IEEE API 수집기 (Python 3.8+, 표준 라이브러리만 사용)
collector/classify.py           ADC/DAC 판별, 아키텍처·응용 태깅, 성능 수치 추출 규칙
collector/venues.json           대상 venue와 IEEE API 질의 조건
scripts/update.sh               랩 서버 cron용: 수집 → 커밋 → push
cache/                          IEEE 원본 응답 (초록 포함, git 제외, 랩 서버에만 보관)
```

## 동작 방식

1. **초기 수집**: `collector/venues.json`의 `since_year`(현재 1997)부터 venue별·연도별로 전체 논문을 받아옵니다. 표준 API 키는 하루 호출 수가 제한되어 있어 하루 190회까지만 쓰고 멈춘 뒤, 다음 날 이어서 받습니다. 30년치는 며칠 걸립니다.
2. **월간 갱신**: 초기 수집이 끝나면 IEEE에 새로 등록된 논문(insert date 기준)만 받아옵니다. 한 번에 수십 회 호출이면 충분합니다. `collector/venues.json`에 venue를 새로 추가하거나 `since_year`를 앞당기면, 다음 실행 때 빠진 venue·연도만 먼저 받아옵니다.
3. **분류**: 제목·초록·IEEE 색인어로 ADC/DAC 여부를 판별하고 아키텍처(SAR, NS-SAR, Pipelined-SAR, TI, CT-ΔΣ, VCO 등)와 응용(SerDes, RF, Bio, CIS, NAND, CIM 등)을 태깅합니다. 제목과 초록에서 해상도, f<sub>s</sub>, SNDR, 전력, 공정, FoM을 정규식으로 뽑아 energy plot에 씁니다. 초록은 분류에만 쓰고 공개 데이터에는 넣지 않습니다.
4. **공개**: `data/*.json`이 바뀌면 커밋·push하고, GitHub Pages가 자동으로 반영합니다.

## 랩 서버 설정 (1회)

서버의 Claude Code에 맡길 때는 [docs/server-setup.md](docs/server-setup.md)를 따르게 하면 됩니다. 작업 규칙은 [CLAUDE.md](CLAUDE.md)에 있습니다. 직접 하실 때는 아래 순서대로 하시면 됩니다.

### 1. 저장소 받기 (deploy key 사용)

서버에서 이 저장소에만 쓰기 권한이 있는 SSH 키를 만듭니다.

```bash
ssh-keygen -t ed25519 -f ~/.ssh/adc_census -N "" -C "adc-census@lab-server"
cat ~/.ssh/adc_census.pub
```

출력된 공개키를 GitHub 저장소 **Settings → Deploy keys → Add deploy key**에 붙여넣고 **Allow write access**를 체크합니다. 그다음:

```bash
cat >> ~/.ssh/config <<'EOF'
Host github-adc-census
  HostName github.com
  User git
  IdentityFile ~/.ssh/adc_census
  IdentitiesOnly yes
EOF

git clone github-adc-census:mixedcas-lab/adc-census.git ~/adc-census
cd ~/adc-census
git config user.name  "MCAS Lab bot"
git config user.email "연구실-메일-주소"
```

### 2. IEEE API 키 저장

키는 저장소에 절대 커밋하지 않고 서버의 개인 설정 파일에만 둡니다.

```bash
mkdir -p ~/.config/adc-census
echo 'IEEE_API_KEY=여기에_키' > ~/.config/adc-census/env
chmod 600 ~/.config/adc-census/env
```

### 3. 첫 실행

```bash
cd ~/adc-census
python3 -m unittest discover -s collector      # 오프라인 테스트
scripts/update.sh                               # 초기 수집 시작 (하루 한도까지)
python3 collector/collect.py --status           # 진행 상황 확인
```

### 4. cron 등록

매일 실행하도록 등록해 두면, 초기 수집 중에는 매일 이어서 받고, 끝난 뒤에는 **매달 15일**에만 실제로 갱신합니다. 15일에 서버가 꺼져 있었으면 다음에 실행되는 날 갱신합니다.

```bash
mkdir -p ~/adc-census/logs
crontab -e
# 아래 한 줄 추가 (매일 06:17)
17 6 * * *  $HOME/adc-census/scripts/update.sh >> $HOME/adc-census/logs/update.log 2>&1
```

갱신 날짜를 바꾸려면 cron 줄에 `UPDATE_DAY=1`처럼 환경변수를 넣습니다(1~28일).

## GitHub Pages 켜기 (1회)

저장소 **Settings → Pages → Build and deployment**에서 Source를 **Deploy from a branch**, Branch를 **main / (root)**로 지정합니다. 몇 분 뒤 위 사이트 주소로 열립니다.

무료 플랜에서는 저장소가 Public이어야 Pages가 동작합니다.

## 그래프와 Murmann Survey

사이트 상단 그래프는 Chart 메뉴에서 고릅니다. Murmann ADC Performance Survey의 다섯 가지 그래프(Energy, FoM<sub>S</sub> vs. f<sub>snyq</sub>, Aperture, FoM<sub>S</sub> 추세, jitter 추세)와 x·y축을 직접 고르는 Custom이 있습니다. 기준선(envelope, jitter 선)은 Survey 저장소의 노트북과 같은 방식으로 계산합니다.

Survey 데이터는 수집기가 `data/papers.json`에 흡수합니다.

- `collector/murmann.py`가 https://github.com/bmurmann/ADC-survey 의 최신 엑셀을 주 1회 받아 `data/murmann.json`으로 바꿉니다(ABSTRACT 열은 가져오지 않음).
- `collect.py`가 DOI로 논문을 맞춰 Survey 수치(SNDR, f<sub>s</sub>, f<sub>snyq</sub>, 전력, FoM, 공정, 면적, f<sub>in</sub>)로 자동 추출값을 바꾸고, 그 필드를 `sv`에 적습니다. 한 논문에 설계가 여러 행이면 FoM<sub>S</sub>가 가장 높은 행을 씁니다. Survey에 있는 논문은 분류 규칙과 관계없이 core ADC가 됩니다.
- 아직 IEEE에서 받지 않은 Survey 논문은 `m:<DOI>` id로 목록에 들어가고, 수집되면 IEEE 기록에 자동으로 합쳐집니다.
- 우선순위: `annotations.csv`(사람 검수) > Survey > 자동 추출. 그래프에서 채운 점은 Survey나 검수 값, 테두리 점은 자동 추출 값입니다.

Survey는 BSD 3-Clause 라이선스이며 사이트 하단에 저작권과 인용 문구를 표시합니다.

## 검수 값 넣기 (학생용)

자동 추출 수치는 회색으로, 검수한 수치는 진한 색으로 표시됩니다. GitHub 웹에서 `data/annotations.csv`를 열어 연필 아이콘으로 바로 편집하면 됩니다. 수집기를 다시 돌릴 필요 없이 사이트에 즉시 반영됩니다.

| 열 | 내용 |
|---|---|
| `id` | IEEE article number (Xplore 주소 끝의 숫자) |
| `exclude` | `1`이면 목록에서 제외 (오탐) |
| `kind` | `ADC` 또는 `DAC` |
| `arch`, `app` | 여러 개면 `;`로 구분 (예: `TI;SAR`) |
| `res`, `fs`, `bw`, `sndr`, `p`, `node`, `foms`, `fomw` | 단위: b, S/s, Hz, dB, W, nm, dB, fJ/conv-step. `1G`, `500M`, `8.4m`, `3.7u` 같은 접미사 사용 가능 |
| `sndr_hf`, `fin`, `area` | 고주파 입력에서의 SNDR(dB), 그때의 입력 주파수(Hz), 면적(mm²). Aperture·jitter 그래프에 쓰임 |
| `cal` | `1`이면 보정 기법 사용, `0`이면 미사용 (비우면 자동 판정) |
| `note`, `by` | 메모, 검수자. 메모는 목록에 표시되고 검색창에서도 찾을 수 있습니다 |

예:

```csv
id,exclude,kind,arch,app,res,fs,bw,sndr,p,node,foms,fomw,note,by
10912345,,,TI;SAR,Wireline/SerDes,8,64G,,38.2,410m,5,,,"Nyquist SNDR",홍길동
10954321,1,,,,,,,,,,,,PLL paper,홍길동
```

## 수집 연도 범위 바꾸기

`collector/venues.json` 맨 위의 `"since_year"`가 수집 시작 연도입니다. GitHub 웹에서 이 값만 고쳐 커밋하면 다음 cron 실행 때 반영됩니다.

- 앞당기면(예: 1997 → 1990) 빠진 연도를 하루 API 한도 안에서 며칠에 걸쳐 받아옵니다.
- 늦추면(예: 1997 → 2010) 그 이전 논문이 사이트에서 빠집니다. 서버 캐시는 남아 있으므로 다시 앞당기면 API 호출 없이 돌아옵니다.
- 학회지 이름·ISSN이 바뀐 해는 질의마다 `from`/`to`로 나눠 두었습니다(TCAS-I/II는 2004년, VLSI Symposium은 2022년 통합).

사이트에서는 From/To 선택으로 보고 싶은 연도만 골라 볼 수 있습니다.

## 분류 규칙 고치기

오탐·누락이 보이면 `collector/classify.py`의 정규식이나 `collector/venues.json`을 고친 뒤, API를 다시 부르지 않고 캐시에서 재분류합니다.

```bash
python3 collector/collect.py --reclassify
python3 -m unittest discover -s collector
```

규칙을 바꿀 때는 `collector/test_collector.py`에 해당 사례를 테스트로 추가해 두면 이후 회귀를 막을 수 있습니다.

## 데이터 필드 (`data/papers.json`)

| 키 | 내용 |
|---|---|
| `id`, `doi`, `url` | IEEE article number, DOI, Xplore 링크 |
| `t`, `v`, `vt` | 제목, venue 약칭, 원래 출판물 이름 |
| `y`, `d` | 출판 연도, 출판 월(`YYYY-MM`) |
| `au`, `org`, `cn` | 저자, 소속 기관, 국가 |
| `k`, `lv` | `ADC`/`DAC`, `core`(제목·색인어에 변환기) 또는 `related`(초록에서만 언급) |
| `ar`, `ap`, `cal` | 아키텍처, 응용, 보정 기법 여부 |
| `s` | 추출 수치: `res`, `fs`, `bw`, `sndr`, `enob`, `p`, `node`, `foms`, `fomw` |
| `ct`, `first`, `ins` | J/C/EA(early access), 처음 수집한 날, IEEE 등록일 |

### 수치 수정 요청

- 사이트의 각 논문 아래 **Report a fix**를 누르면 GitHub 이슈 작성 화면이 열립니다. 논문 id, 현재 값과 출처, annotations.csv 행 형식이 미리 채워져 있으니 고칠 항목·값·근거(표·그림·쪽)만 적으면 됩니다(GitHub 계정 필요).
- 연구실은 이슈를 확인해 `data/annotations.csv`에 행을 추가하고 이슈를 닫습니다. 저장소 쓰기 권한이 있으면 annotations.csv를 직접 고쳐도 됩니다.
- 수신기·송수신기·SoC·센서 논문처럼 **ADC가 시스템의 블록인 논문**(`ADC inside a system`)은 논문의 전력·속도·FoM이 시스템 전체 값이므로 자동·AI 수치를 표시하지 않고 "—"로 둡니다. Survey 값과 사람이 검수한 값은 표시합니다.

### 값의 출처와 삭제

- 사이트는 값마다 출처를 표시합니다: `T` 제목, `A` 초록(둘 다 정규식 자동 추출, 회색), `S` Murmann Survey, `AI` AI 도구 추출(보라색 기울임, 미검수), `✓` 연구실 검수(진한 색).
- annotations.csv의 행은 기본적으로 **사람 검수**로 처리합니다. `by` 열에 Codex·GPT·Claude 같은 AI 도구 이름이 있거나 `source` 열이 `ai`이면 **AI 추출**로 처리합니다.
- 값이 서로 다를 때 우선순위: 사람 검수 > Murmann Survey > AI 추출 > 정규식(제목·초록). AI 값은 더 높은 출처를 덮어쓰지 않고, 다르면 목록에 `Review` 태그를 붙입니다. AI 행의 메모는 표시하지 않습니다.
- 칸을 비우면 기존 값을 유지합니다. **잘못된 자동값을 지우려면 `-`(또는 `NA`)** 를 넣습니다. 사이트에는 "—"로 표시됩니다.
- 사이트의 Values 필터로 검수된 값만 보거나, 그래프에서 검수 값(채운 점)·AI 값(점선 테두리)·자동 값(테두리)을 구분해 볼 수 있습니다.

### 태그 입력 요령

- `arch`, `app`을 채우면 자동 태그를 **대체**합니다. 자동 태그 중 맞는 것도 함께 적으세요.
- 대소문자·하이픈·공백은 구분하지 않고, 자주 쓰는 약칭도 인식합니다: `DSM`→ΔΣ, `CT-DSM`→CT-ΔΣ, `pipe-sar`→Pipelined-SAR, `ti`→TI, `serdes`→Wireline/SerDes, `cis`→Image sensor.
- `cal` 열이 헤더에 없으면 헤더 줄 끝에 `,cal`을 붙이고 쓰면 됩니다(열 순서는 상관없음).

## 감사의 글

이 사이트의 아이디어를 주신 중앙대학교 김민휘 교수님께 감사드립니다.

## 참고

- IEEE Xplore API 이용약관을 따릅니다. 초록과 본문은 공개하지 않고, 서지 정보와 Xplore 링크만 제공합니다.
- 자동 추출 수치는 오류가 있을 수 있습니다. 인용·비교에는 원문을 확인하세요.

## Conference deadline bar

The bar above the masthead is shared by all Census sites. `deadlines.js`, `deadlines.css` and `deadlines.json` live in this repository, and every Census page loads them with one line:

```html
<script src="https://mixedcas-lab.github.io/adc-census/deadlines.js?v=6" data-field="pll" defer></script>
```

Editing `deadlines.json` takes effect on all pages at once (it is always fetched fresh). After changing `deadlines.js` or `deadlines.css`, bump `?v=` in all eight `index.html` files so browsers drop their cached copy.

`deadlines.json` is edited by hand (the collector does not touch it):

- `fields`: the Census pages a conference appears on (`adc`, `dac`, `pll`, `ldo`, `pmic`, `wireline`, `eda`, `accel`).
- `due`: the deadline exactly as published, with its UTC offset (e.g. `2026-11-16T23:59:00-08:00`) and `tz` for the label. The bar shows a live KST countdown.
- `est`: `YYYY-MM` for a cycle that is not announced yet. Shown as `~Apr 2027`, without a countdown.
- When a `due` passes, the bar rolls that conference over to next year's edition as an estimate until the file is updated.
- The nearest confirmed deadline is highlighted. Cards rotate every few seconds when they do not all fit (sized so that none is cut off); swipe or drag sideways to move them by hand.

Some architecture and EDA entries were cross-checked against AI Hardware Deadlines by Prof. Donghyeon Han (Chung-Ang University).
