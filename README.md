# Generic API Tester

Generic API Tester は、API仕様を `api-assets.json` に定義してブラウザからREST APIをテストするための軽量ツールです。
APIごとにHTMLやJavaScriptを書き換えず、URL、HTTPメソッド、送信形式、ヘッダー、パラメータ、入力UIなどをJSONで追加できます。

ブラウザからのAPI呼び出しは同梱のPythonローカルプロキシを経由します。CORSの影響を避けつつ、`server-config.json` で許可したホストだけへアクセスできます。

## 主な機能

- JSONによるAPI定義
- GET / POSTなどのHTTPメソッド
- Query / JSON / Form / Multipart / Binary / XML送信
- オブジェクト・配列を含むネストパラメータ
- `string` / `number` / `boolean` / `file` の型指定
- `required` / `nullable` / `default`
- テキスト、リストボックス（`select`）、ラジオボタン（`radio`）入力
- Booleanの3状態入力（未指定 / true / false）
- UUID・日時などの `special` 自動生成
- `special.regenerate` による再生成タイミング制御
- Base64 / Quoted-Printableエンコード
- Bearer Token / API Key認証
- 送信内容のプレビューとコピー
- レスポンス表示とコピー
- 名前付き保存・JSONファイル保存
- 直近10件の実行履歴
- localStorage容量不足時の履歴自動調整
- READMEの画面内表示

## 動作環境

- Windows 10 / 11
- Python 3
- Google Chrome / Microsoft Edgeなどのモダンブラウザ

Python側は標準ライブラリのみを使用し、フロントエンドもjQueryなどの外部JavaScriptライブラリには依存しません。

## セットアップと起動

1. ZIPを任意のフォルダへ展開します。
2. `start-server.bat` をダブルクリックします。
3. ブラウザで Generic API Tester が開きます。

通常は次のURLで起動します。

```text
http://127.0.0.1:8000/
```

`api-tester.html` を `file://` で直接開かないでください。APIプロキシやREADME読込など、ローカルサーバーを前提とする機能があります。

## 基本的な使い方

1. 「API定義」でテストするAPIを選択します。
2. 必要なパラメータを入力します。
3. 「送信内容を生成」で実際に送るURLやBodyを確認します。
4. 「API実行」でリクエストを送信します。
5. 「レスポンス」でHTTPステータスと応答内容を確認します。

必要に応じて、現在の入力内容を名前付き保存したり、JSONファイルへ書き出したりできます。

## ファイル構成

```text
generic-api-tester/
├─ README.md
├─ LICENSE
├─ NOTICE
├─ .gitignore
├─ start-server.bat
├─ test-server.py
├─ server-config.json
└─ html/
   ├─ api-tester.html
   └─ assets/
      └─ api-assets.json
```

| ファイル | 用途 |
|---|---|
| `html/api-tester.html` | API Tester本体 |
| `html/assets/api-assets.json` | API定義 |
| `test-server.py` | ローカルHTTPサーバー / APIプロキシ |
| `server-config.json` | サーバー・プロキシ設定 |
| `start-server.bat` | Windows起動用 |

## API定義

APIは `html/assets/api-assets.json` に定義します。

```json
{
  "employee-search": {
    "label": "社員検索",
    "method": "POST",
    "paramLocation": "body",
    "bodyType": "json",
    "serialization": "native",
    "url": "https://example.com/api/employees",
    "headers": {
      "Accept": "application/json"
    },
    "params": []
  }
}
```

### 基本パラメータ

```json
{
  "name": "EmployeeCode",
  "label": "社員コード",
  "type": "value",
  "valueType": "string",
  "required": true,
  "nullable": false,
  "default": "E00125",
  "placeholder": "例: E00125"
}
```

| 項目 | 意味 |
|---|---|
| `name` | APIへ送信するパラメータ名 |
| `label` | 画面表示名 |
| `type` | `value` / `object` / `array` |
| `valueType` | `string` / `number` / `boolean` / `file` |
| `required` | パラメータを必須とするか |
| `nullable` | 必須パラメータで `null` を許容するか |
| `default` | 初期値 |
| `placeholder` | 入力欄の補助表示 |
| `enabled` | `false` の場合は入力・送信対象外 |

`value` は従来定義との互換用として利用できます。新しい定義では `default` の利用を推奨します。

### required / nullable

未入力・未選択時は次のように扱います。

| required | nullable | 動作 |
|---|---|---|
| `false` | `false` | パラメータを送信しない |
| `false` | `true` | パラメータを送信しない |
| `true` | `false` | 入力エラー |
| `true` | `true` | `null` を送信 |

`required` は「項目を送信する必要がある」、`nullable` は「その値としてnullを許す」という意味です。

### オブジェクト

```json
{
  "name": "Applicant",
  "label": "申請者",
  "type": "object",
  "children": [
    {
      "name": "EmployeeId",
      "label": "社員番号",
      "type": "value",
      "valueType": "string"
    }
  ]
}
```

### 配列

```json
{
  "name": "Approvers",
  "label": "承認者",
  "type": "array",
  "initialItems": 1,
  "item": {
    "type": "object",
    "children": [
      {
        "name": "EmployeeId",
        "label": "社員番号",
        "type": "value",
        "valueType": "string"
      }
    ]
  }
}
```

配列要素は画面から追加・削除できます。

## 入力UI `inputType`

`valueType` は送信するデータ型、`inputType` は画面上の入力方法を表します。

### リストボックス

```json
{
  "name": "Department",
  "label": "部署",
  "type": "value",
  "valueType": "string",
  "inputType": "select",
  "default": "SALES",
  "options": [
    { "value": "SALES", "label": "営業部" },
    { "value": "DEV", "label": "開発部" },
    { "value": "ADMIN", "label": "管理部" }
  ]
}
```

画面には `label` を表示し、APIには `value` を送信します。

### ラジオボタン

```json
{
  "name": "EmploymentType",
  "label": "雇用区分",
  "type": "value",
  "valueType": "string",
  "inputType": "radio",
  "required": true,
  "nullable": true,
  "options": [
    { "value": "REGULAR", "label": "正社員" },
    { "value": "CONTRACT", "label": "契約社員" }
  ]
}
```

`default` がなければ、radioは初期状態で未選択にできます。上記のように `required: true` / `nullable: true` なら、未選択時はパラメータを省略せず `null` を送信します。

未指定を選択肢として明示したい場合は、`options` に未指定用の選択肢を定義できます。

### Boolean

`valueType: "boolean"` は3状態チェックボックスで表示します。

```text
未指定 → true → false → 未指定
```

- 未指定: optionalならパラメータを送信しない
- true: JSON Boolean `true`
- false: JSON Boolean `false`

連続するトップレベルBooleanは、データ構造を変えず画面上だけ同行表示します。オブジェクト内では `layout: "inline"` も使用できます。

## 特殊値 `special`

UUIDや日時など、固定入力ではなく自動生成する値を定義できます。

### UUID

```json
{
  "name": "RequestId",
  "label": "リクエストID",
  "type": "value",
  "special": "uuid",
  "format": "default",
  "regenerate": "eachRequest"
}
```

UUIDの `format` は `default` / `compact` / `braces` / `urn` / `upper` を指定できます。

### 日時

```json
{
  "name": "RequestDateTime",
  "label": "リクエスト日時",
  "type": "value",
  "special": "datetime",
  "format": "yyyy-MM-dd HH:mm:ss.SSS",
  "timezone": "local",
  "regenerate": "eachRequest"
}
```

`timezone` は `local` または `utc` を指定できます。

### regenerate

| 値 | 動作 |
|---|---|
| `ifEmpty` | 値が空の場合だけ生成。省略時の既定動作 |
| `eachRequest` | リクエスト単位で新しい値を生成 |
| `manual` | 「再生成」を行った場合だけ生成し直す |

`eachRequest` では、パラメータ欄に実際のUUIDや日時を固定表示せず、自動生成されることが分かる表示にします。

「送信内容を生成」を押すと値を生成して内部保持し、送信内容には実値を表示します。そのまま「API実行」を押した場合は、確認したものと同じ値を送信します。API実行後は内部値を破棄し、次のリクエストでは新しい値を生成します。

「送信内容を生成」をもう一度押した場合も、新しい `eachRequest` 値を生成します。履歴を読み込んだ場合、過去に送信した実値は履歴の送信内容として確認できますが、次回リクエスト用の値としては復元しません。

## ファイル・エンコード・XML

### ファイル

```json
{
  "name": "file",
  "label": "添付ファイル",
  "type": "value",
  "valueType": "file",
  "required": true,
  "accept": ".pdf,.txt,image/*"
}
```

`multiple: true` で複数ファイルを選択できます。

### bodyType

主な送信形式は次のとおりです。

- `none`
- `json`
- `form`
- `multipart`
- `binary`
- `xml`
- `raw`

`multipart` では `FormData` を使用し、multipart boundaryはブラウザが設定します。

### encoding

ファイルや文字列には必要に応じて次のエンコードを指定できます。

- `none`
- `base64`
- `quoted-printable`

### XML

```json
{
  "bodyType": "xml",
  "xml": {
    "root": "request",
    "declaration": true
  }
}
```

オブジェクトはネスト要素、配列は同名要素の繰り返しとしてXMLを生成します。

## 認証

認証情報は `api-assets.json` に直接書かず、画面から入力します。

Bearer Token:

```json
{
  "auth": {
    "type": "bearer"
  }
}
```

API Key:

```json
{
  "auth": {
    "type": "apiKey",
    "in": "header",
    "name": "X-API-Key"
  }
}
```

`in` には `header` または `query` を指定できます。

## 保存・読込

### 名前付き保存

現在のAPI定義と入力内容をブラウザの `localStorage` に保存します。保存名を空にした場合はAPI名と日時から自動生成します。同名保存時は確認ダイアログを表示します。

### JSONファイル

「ファイル保存」で現在の内容をJSONファイルへ書き出し、「ファイル読込」で復元できます。ブラウザのサイトデータとは独立しているため、バックアップや別PCへの移行にも利用できます。

### 実行履歴

API実行時に直近10件を保存します。履歴にはAPI定義、入力値、実際の送信内容、レスポンス、HTTPステータス、実行日時などを保持します。

個別履歴は確認なしで削除でき、全履歴削除時は確認ダイアログを表示します。

### localStorage容量不足

`localStorage` の容量上限に達しても、既存の保存データや履歴の読み込みは継続できるようにしています。

実行履歴の保存で容量不足になった場合は、古い履歴から削除して再試行します。それでも保存できない場合は容量不足として通知します。履歴保存の失敗をAPI通信そのものの失敗としては扱いません。

大きなレスポンスを繰り返し保存すると容量を消費するため、必要な履歴はJSONファイル等へ退避してください。

## サーバー設定

`server-config.json` でローカルサーバーとプロキシを設定します。

```json
{
  "host": "127.0.0.1",
  "port": 8000,
  "web_root": "html",
  "default_document": "api-tester.html",
  "proxy_path": "/proxy",
  "proxy_timeout": 60,
  "allowed_schemes": [
    "https"
  ],
  "allowed_hosts": [
    "jsonplaceholder.typicode.com",
    "httpbin.org"
  ],
  "open_browser": true
}
```

| 項目 | 意味 |
|---|---|
| `host` | ローカルサーバーの待受アドレス |
| `port` | 待受ポート |
| `web_root` | 公開するWebルート |
| `default_document` | `/` で表示するHTML |
| `proxy_path` | APIプロキシのパス |
| `proxy_timeout` | API通信タイムアウト（秒） |
| `allowed_schemes` | 許可するURLスキーム |
| `allowed_hosts` | プロキシ接続を許可するAPIホスト |
| `open_browser` | 起動時にブラウザを開くか |

新しいAPIホストへ接続する場合は `allowed_hosts` に明示的に追加してください。ワイルドカードで任意ホストを許可する構成は、意図しない中継プロキシ化を避けるため推奨しません。

## 同梱サンプルAPI

`api-assets.json` には、基本的なGET/POSTだけでなく、次の機能を確認できるサンプルを含めています。

- ネストJSON・配列
- 型指定・required / nullable
- `select` / `radio` / Boolean入力
- UUID・日時の `special`
- Multipartファイル送信
- Quoted-Printable
- XML / Base64ファイル
- Bearer認証

公開テストAPIを利用するサンプルは、インターネット接続が必要です。

## Git管理

Pythonの実行・構文チェックで生成されるキャッシュはGit管理対象外です。

```gitignore
__pycache__/
*.py[cod]
```

## License

Apache License 2.0

Copyright 2026 rucola-salad


### 未指定値と `default`

API定義を新規表示したときは `default` を初期値として使用します。保存データ・ファイル・履歴を読み込むときは、保存JSONに存在しないパラメータを「未指定」として復元し、API定義の `default` は再適用しません。Boolean の3状態も `true` / `false` / キーなし（未指定）を区別します。



### 保存データ・履歴とAPI定義の差異

保存データ、インポートファイル、実行履歴を読み込む際は、現在の `api-assets.json` とパラメータ構成を比較します。API定義自体が存在する場合は、共通する項目の読み込みを継続し、差異があれば画面上部のステータス領域に警告を表示します。現在の定義にない保存項目は無視し、保存データにない現在の定義項目は未指定として扱います。ネストした項目は `Application.Applicant.OldField` のようなパスで表示します。

保存時の `assetKey` に対応するAPI定義自体が存在しない場合は、従来どおりエラーとして読み込みを中止します。
