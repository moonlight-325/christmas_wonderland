# gifts/ — 어드벤트 선물에 연결할 외부 프로그램 폴더

`data/advent_contents.json` 의 날짜 항목에 `action` 을 적으면, 선물 상세 화면에 **선물 실행** 버튼이 생기고
이 폴더 안의 프로그램을 실행합니다. 코드를 고칠 필요 없이 JSON 만 바꾸면 됩니다.

```json
{
  "day": 24,
  "title": "크리스마스 이브",
  "action": { "type": "python", "file": "gifts/christmas_tree/main.py" }
}
```

| type | 실행 대상 | 방식 |
|---|---|---|
| `python` | `.py` 파일 | 설치된 Python 으로 실행 (PATH 의 `python.exe` → `py -3` → 일반 설치 위치 순서로 탐색) |
| `executable` | `.exe` 파일 | 그대로 실행 (Windows 전용) |

- `file` 은 **프로그램 폴더(ChristmasWonderland.exe 가 있는 폴더) 기준 상대 경로**이며 반드시 `gifts/` 로 시작해야 합니다.
- 절대 경로, 드라이브(`C:`), 네트워크 경로(`\\server`), `..` 는 허용하지 않습니다. 심볼릭 링크로 `gifts/` 밖을 가리켜도 막습니다.
- 실행한 프로그램은 Christmas Wonderland 와 별개 프로세스입니다. 프로그램이 끝날 때까지 기다리지 않으며, 실행 중에는 버튼이 '실행 중'으로 바뀝니다.
- 프로그램의 작업 폴더는 그 파일이 있는 폴더입니다. 콘솔 창은 열리지 않으므로 창이 있는(GUI) 프로그램을 연결하세요.
- `action` 이 없는 날짜에는 버튼이 나타나지 않습니다. 형식이 잘못된 `action` 은 무시되고 '콘텐츠 설정' 창에 경고가 표시됩니다.

```
ChristmasWonderland/
├── ChristmasWonderland.exe
├── gifts/
│   └── christmas_tree/
│       ├── main.py
│       └── christmas_tree.exe
├── data/
└── assets/
```
