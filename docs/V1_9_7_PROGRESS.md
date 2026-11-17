# v1.9.7 진행 현황 — 최종 정리 (기능 변경 없음)

기준: v1.9.6 UI Stage 7. 버전은 `core/version.py` 한 곳(1.9.7)에서만 정의합니다.

| 단계 | 내용 | 상태 |
|---|---|---|
| 1단계 | 파일 간 의존성 분석 (import 그래프, pyflakes, vulture) | 완료 (코드 변경 없음) |
| 2단계 | 미사용 파일·코드·import 삭제 | 완료 |
| 3단계 | 불필요한 툴팁 삭제 | 완료 |
| 4단계 | 버전 1.9.7 정렬, 테스트 추가/정렬, README, 최종 ZIP | 완료 |

## 1단계 분석 결과
- `desktop/` (8개 파일, 약 1,050줄): 어떤 모듈·테스트·build.bat·문자열 참조에서도 쓰이지 않음 → 삭제 대상
- 미사용 함수: `Pile.height_at`, `SnowSim._trim_extra`, `snowglobe.model.ground_contains`, `pixel_ui.draw_text`
- 테스트에서만 쓰이는 함수(`mass_balance`, `relax_all`, `counts`, `shaking`)는 검증용이라 유지
- 그 외 vulture 가 알린 `paintEvent`/`mouseMoveEvent` 등은 Qt 가 호출하는 재정의라 삭제하지 않음

## 2단계 삭제 목록
- 파일: `desktop/` 전체
- 함수: 위 4개
- import: `QRect`(clockface/window), `QColor`·`QPen`(snowglobe/widget), `QLabel`·`QWidget`·`QVBoxLayout` 중복·`PALETTES`·`KIND_SPRITE`(settings_window), `QLabel`(snowglobe_window), `QPointF`(wind_dial), `AVAILABLE`(advent/calendar_page), `json`(tools/generate_advent_images), `KIND_NAME`(decor/items)
- 지역 변수·인자: `sim`(overlay), `thick`(lights), `ox`·`role_part`(snowman/render), `dy`(calendar_page), `preview_item`(snowglobe/render), 쓰이지 않던 `tips` 사전(auto_weather_page), 자리표시자 없는 f-string(advent/events)
- 유지: `import decor.sprites` (스프라이트 등록용 부수효과 import)

## 3단계 툴팁
- 삭제: 시계 창·장식 창의 '잠김' 호버 툴팁 (커서 모양으로 같은 정보 표시)
- 유지: 끄는 동안 좌표/크기 표시, 화면 밖 보정 안내, 아이콘만 있는 버튼(미리 듣기·내 음원·초기화), 눈사람 색상 칸 이름, 긴 항목 이름, 트레이 툴팁

## 4단계 테스트
- 추가: `tests/test_v197.py` (버전, README, desktop 제거, 삭제 항목, 전체 컴파일)
- 정렬: `test_stage5_ui.py`(잠김 툴팁 없음), `test_stage4_ui.py`(낡은 '[꾸미기 모드]' 문구 검사를 현재 문구로 — v1.9.6 에서도 이미 실패하던 테스트)
- 미검증: `tests.test_gui_smoke.GuiSmoke` 는 샌드박스에 오디오 장치가 없어 `audio/manager.py` 에서 세그폴트(v1.9.6 원본에서도 동일). Windows 실기 확인 필요
