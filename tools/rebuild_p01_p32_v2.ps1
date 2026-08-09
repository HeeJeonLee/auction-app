$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$v2Path = Join-Path $root 'docs/05_MVP_권리분석32p_취하18p_검수본_v2.md'
$v1Path = Join-Path $root 'docs/05_MVP_권리분석32p_취하18p_초안_v1.md'

$v2 = Get-Content -Raw -Encoding UTF8 $v2Path
$v1 = Get-Content -Raw -Encoding UTF8 $v1Path

$titles = @{}
[regex]::Matches($v1, '(?m)^##\s+p(\d{2})\.\s*(.+)$') | ForEach-Object {
    $n = [int]$_.Groups[1].Value
    if ($n -ge 1 -and $n -le 32) {
        $titles[$n] = $_.Groups[2].Value.Trim()
    }
}

function Get-Spec([int]$n) {
    switch ($n) {
        1 { return @{rule='RA-01/RA-02/RA-03';stage='권리분석';goal='사건 식별키 충돌 방지';must='사건번호, 법원명, 주소';sop='사건번호 정규화 -> 법원명 표준화 -> 주소 동/호 분리';fail='3키 중 1개라도 공란이면 HOLD';pass='사건키 중복 0건'} }
        2 { return @{rule='RA-01';stage='권리분석';goal='사건번호 정규화 일관성 확보';must='사건번호 원문, OCR 사건번호';sop='YYYY타경NNNN 패턴 검증 -> 보조번호 분리 저장';fail='패턴 불일치+원문 미확인';pass='정규화 성공 및 원문 근거 기록'} }
        3 { return @{rule='RA-02/RA-03/RA-06';stage='권리분석';goal='법원/주소 관할 정합성 검증';must='법원명, 주소';sop='관할 추정 -> 주소 시군구 추출 -> 수도권 토큰 대조';fail='관할 불일치인데 근거 없음';pass='관할 일치 또는 보완사유 기재'} }
        4 { return @{rule='RA-04';stage='권리분석';goal='감정가 하한 필터 정확화';must='감정가, 금액 단위';sop='숫자 파싱 -> 단위 교정 -> 5억 하한 비교';fail='5억 미만 또는 미입력';pass='감정가>=5억 및 단위 근거 명시'} }
        5 { return @{rule='RA-05';stage='권리분석';goal='50억 초과 대형딜 분리';must='감정가';sop='상한 비교 -> 대형트랙 플래그 -> 일반 큐 제외';fail='초과건 일반 큐 잔존';pass='대형딜 분리 저장'} }
        6 { return @{rule='RA-06';stage='권리분석';goal='수도권 범위 외 건 자동 분리';must='법원명, 주소';sop='서울/경기/인천 토큰 판정';fail='비수도권 GO';pass='권역 판정과 상태 일치'} }
        7 { return @{rule='RA-07';stage='권리분석';goal='부채총액 필수화';must='청구금액, 채권최고액, 부채총액';sop='금액 추출 -> 대표 부채값 확정 -> 출처 기록';fail='부채총액 0 또는 공란';pass='부채총액>0 및 출처 태그'} }
        8 { return @{rule='RA-08';stage='권리분석';goal='시세 기준값 확보';must='KB시세 또는 대체시세, 기준일';sop='KB 우선 -> 대체시세 보완 -> 기준일 노후도 점검';fail='시세값 없음';pass='시세+기준일+출처 3요소'} }
        9 { return @{rule='RA-09';stage='권리분석';goal='고LTV 사건 보수 분기';must='부채총액, KB시세/감정가';sop='LTV 계산 -> 0.85 임계치 비교';fail='LTV 계산 불가인데 GO';pass='LTV 수치와 판정 일치'} }
        10 { return @{rule='RA-10';stage='권리분석';goal='권리플래그 다중 경고';must='근저당/압류/가압류/가처분/임차권/전세권/가등기';sop='예 개수 집계 -> 3초과 정밀검토 큐';fail='리스크 과다인데 GO';pass='리스크 개수와 검토큐 연동'} }
        11 { return @{rule='RA-11';stage='데이터정합성';goal='매각기일 신뢰성 확보';must='매각기일 원문, 파싱값, 잔여일수';sop='날짜 형식 검증 -> 잔여일수 재계산 -> 음수 경고';fail='날짜 미확정 상태 우선순위 계산';pass='매각기일/잔여일수 교차확인'} }
        12 { return @{rule='RA-12';stage='데이터정합성';goal='물건번호 혼합 방지';must='사건번호, 물건번호, 주소';sop='사건-물건 조합키 생성 -> 중복 병합 차단';fail='물건번호 누락 병합';pass='조합키 고유성'} }
        13 { return @{rule='RA-13';stage='데이터정합성';goal='권리요약 품질 보장';must='권리요약, 권리플래그';sop='요약 공란/반복문 검사 -> 플래그 기반 보강';fail='권리요약 공란';pass='핵심 리스크 2개 이상 포함'} }
        14 { return @{rule='RA-14';stage='데이터정합성';goal='주요채권자 식별 필수화';must='주요채권자 원문';sop='명칭 표준화 -> 유형 태깅';fail='채권자 미상인데 스크립트 생성';pass='채권자명+유형 동시 확정'} }
        15 { return @{rule='RA-15';stage='데이터정합성';goal='감정가-최저가 정합성 검사';must='감정가, 최저매각가격';sop='비율 계산 -> 비정상 구간 경고';fail='최저가 비정상인데 통과';pass='가격 비율 허용범위 확인'} }
        16 { return @{rule='RA-16';stage='데이터정합성';goal='예상낙찰가 근거 확보';must='낙찰예상가, 산출근거';sop='예상가 존재 확인 -> 근거 라인 점검';fail='예상가 없이 회수비교 수행';pass='예상가+근거 동시 보관'} }
        17 { return @{rule='RA-17';stage='데이터정합성';goal='부채 역전 위험 식별';must='부채총액, KB시세';sop='부채/시세 비율 계산 -> 1.0 초과 라벨';fail='역전인데 저위험';pass='역전 라벨과 판정 일치'} }
        18 { return @{rule='RA-18';stage='데이터정합성';goal='등기부 정밀검토 자동표기';must='권리요약, 권리플래그';sop='중대 권리 탐지 -> 열람필수 태그 부여';fail='중대권리인데 열람필수 누락';pass='위험사유와 태그 연동'} }
        19 { return @{rule='RA-19';stage='데이터정합성';goal='아파트명 매칭 안정화';must='아파트명, 주소';sop='단지명 추출 -> 주소 토큰 대조';fail='아파트명 미상 상태 비교';pass='단지명/주소 토큰 정합'} }
        20 { return @{rule='RA-20';stage='데이터정합성';goal='분석 준비도 게이트';must='핵심 필드 채움률';sop='채움률 계산 -> 기준 미달 HOLD';fail='채움률 미달인데 결론 생성';pass='준비도 라벨과 수치 일치'} }
        21 { return @{rule='RA-21';stage='리스크점수화';goal='권리 위험 정량화';must='권리 플래그, 가중치';sop='가중치 합산 -> 위험등급 산출';fail='근거 없는 임의점수';pass='계산식과 로그 보관'} }
        22 { return @{rule='RA-22';stage='리스크점수화';goal='점유/명도 리스크 반영';must='점유정보, 담당자메모';sop='점유 유무 판정 -> 명도 난이도 라벨';fail='점유 미상인데 저위험';pass='점유 라벨+메모 존재'} }
        23 { return @{rule='RA-23';stage='리스크점수화';goal='배당 비교 4요소 완결성';must='감정가, 최저가, 예상가, 부채';sop='4요소 존재검사 -> 누락리포트 생성';fail='누락 상태 배당표 출력';pass='4요소 완비'} }
        24 { return @{rule='RA-24';stage='리스크점수화';goal='유찰 이력 반영 보정';must='유찰횟수, 낙찰예상가';sop='유찰 기반 보정계수 적용';fail='유찰 다수인데 보정 없음';pass='보정 전후 로그'} }
        25 { return @{rule='RA-25';stage='리스크점수화';goal='예상가 급변 근거 강제';must='기존/보정 예상가';sop='변동률 계산 -> 임계치 초과 근거 요구';fail='10%+ 변동 무근거';pass='변동사유 기록'} }
        26 { return @{rule='RA-26';stage='리스크점수화';goal='LTV 경계구간 운영';must='LTV';sop='0.80~0.85 경계 식별 -> HOLD 우선';fail='경계구간 GO';pass='경계 라벨+보완조건'} }
        27 { return @{rule='RA-27';stage='리스크점수화';goal='권리-채권자 일치 검증';must='권리요약, 주요채권자';sop='권리 특성과 채권자 성격 교차검증';fail='유형 불일치 템플릿 사용';pass='유형 일치 확인'} }
        28 { return @{rule='RA-28';stage='리스크점수화';goal='고가물건 근거 강화';must='감정가, 근거 라인 수';sop='30억+ 여부 -> 최소 근거 검사';fail='고가물건 근거 부족';pass='근거 2개 이상'} }
        29 { return @{rule='RA-29';stage='리스크점수화';goal='규칙근거 최소치 보장';must='evidence 라인';sop='근거 라인 카운트 -> 미달 시 보완요청';fail='근거 부족 보고서 출력';pass='근거 라인 기준 충족'} }
        30 { return @{rule='RA-30';stage='리스크점수화';goal='근거 포맷 표준화';must='규칙근거 문자열';sop='표준 패턴 정규식 검증';fail='포맷 불일치';pass='표준 포맷 100%'} }
        31 { return @{rule='RA-31';stage='리스크점수화';goal='점수-판정 임계치 일관화';must='규칙점수, 규칙판정';sop='GO/HOLD/DROP 임계치 교차검증';fail='점수-판정 불일치';pass='임계치 일치'} }
        32 { return @{rule='RA-32';stage='리스크점수화';goal='결론문 리스크/권고 결합';must='risks, recommendations, 결론문';sop='리스크 2개+권고 1개 포함 여부 검사';fail='결론문에 리스크 누락';pass='결론문 구조 충족'} }
        default { throw "Unsupported page: $n" }
    }
}

$pre = @(
    '# MVP 매뉴얼 50P 검수본 v2',
    '',
    '범위: 서울/수도권 아파트, 감정가 5억~50억(초과건 별도 트랙)',
    '목표: OCR 결과를 규칙 엔진에 직접 연결해 점수/판정/취하 스크립트를 생성하고, 검수자가 즉시 반려/보완 결정을 내릴 수 있는 실무 문서를 제공한다.',
    '버전: MVP-2026.08-v2',
    '',
    '---',
    ''
) -join "`r`n"

$builder = New-Object System.Text.StringBuilder
$null = $builder.AppendLine($pre)
for ($n = 1; $n -le 32; $n++) {
    $p = 'p{0:d2}' -f $n
    $title = if ($titles.ContainsKey($n)) { $titles[$n] } else { "페이지 $n" }
    $s = Get-Spec $n

    $null = $builder.AppendLine("## $p. $title")
    $null = $builder.AppendLine("- 문서 단계: $($s.stage)")
    $null = $builder.AppendLine("- 규칙ID: $($s.rule)")
    $null = $builder.AppendLine("- 핵심목표: $($s.goal)")
    $null = $builder.AppendLine('')
    $null = $builder.AppendLine('### 필수 입력')
    $null = $builder.AppendLine("- $($s.must)")
    $null = $builder.AppendLine('')
    $null = $builder.AppendLine('### 검증 절차(SOP)')
    $null = $builder.AppendLine("- $($s.sop)")
    $null = $builder.AppendLine('- 원문 캡처, OCR 추출값, 규칙 evidence를 같은 사건 키로 대조한다.')
    $null = $builder.AppendLine('')
    $null = $builder.AppendLine('### 반려/보류 기준')
    $null = $builder.AppendLine("- $($s.fail)")
    $null = $builder.AppendLine('- 보완 요청 시 재수집 필드와 마감시각을 같이 남긴다.')
    $null = $builder.AppendLine('')
    $null = $builder.AppendLine('### 승인 기준')
    $null = $builder.AppendLine("- $($s.pass)")
    $null = $builder.AppendLine('- rule_version, 규칙근거, 담당자메모가 함께 저장되면 승인한다.')
    $null = $builder.AppendLine('')
    $null = $builder.AppendLine('### 검수 로그 템플릿')
    $null = $builder.AppendLine("- [$p] [GO/HOLD/DROP] [핵심근거 2줄] [보완요청 1줄] [검수자/시각]")
    $null = $builder.AppendLine('')
    $null = $builder.AppendLine('---')
    $null = $builder.AppendLine('')
}

$p33on = [regex]::Match($v2, '(?ms)^##\s+p33\..*$').Value
if (-not $p33on) { throw 'p33~end block not found in v2 file' }

$newDoc = $builder.ToString() + $p33on
Set-Content -Path $v2Path -Value $newDoc -Encoding UTF8
Write-Output 'rebuilt p01-p32 and preserved p33-p50'
