# keirin-analyzer

WINTICKETの競輪レース結果を毎日収集し、SQLiteへ保存するMVPです。

## セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 実行

```powershell
python -m src.scraper
```

日付を指定する場合:

```powershell
python -m src.scraper --date 2026-06-09
```

## 保存先

- DB: `data/keirin.db`
- 分析ページ: `docs/index.html`, `docs/venues.html`, `docs/car_numbers.html`, `docs/payouts.html`, `docs/racers.html`, `docs/custom.html`
- ログ: `logs/collector.log`, `logs/error.log`

## GitHub Actions

`.github/workflows/collect.yml` により、毎日 23:50 JST に自動実行します。

実行後に `docs/*.html` も更新されます。GitHub Pagesを使う場合は、Repository settingsの
Pagesで公開元を `main` ブランチの `/docs` に設定してください。
