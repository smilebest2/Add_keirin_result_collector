# keirin-analyzer

競輪レース結果を毎日収集し、SQLiteへ保存してGitHub Pagesで分析レポートを公開します。

## セットアップ

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
```

## ローカル実行

```powershell
python -m src.scraper
python -m src.analysis
```

日付を指定する場合:

```powershell
python -m src.scraper --date 2026-06-10
```

## 保存先

- DB: `data/keirin.db`
- 分析ページ: `docs/*.html`
- ログ: `logs/collector.log`, `logs/error.log`, `logs/results_rendered.html`

## GitHub Actions

`.github/workflows/collect.yml` により、毎日 23:40 JST に自動取得します。

push後の自動取得は行いません。手動で取得したい場合は、GitHub Actionsの `Collect Keirin Results` から `Run workflow` を実行します。

取得済みデータを削除したい場合は、GitHub Actionsの `Reset Keirin Data` から `Run workflow` を実行します。

GitHub Pagesは `main` ブランチの `/docs` を公開元にします。
