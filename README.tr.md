# MaterialScope

**[English](README.md) · [Türkçe](README.tr.md)**

MaterialScope; DSC, TGA, DTA, FTIR, Raman ve XRD verileriyle tekrarlanabilir malzeme karakterizasyonu çalışmaları yürütmek için geliştirilmiş açık kaynaklı bir Python çalışma ortamıdır. Veri içe aktarma, işleme, karşılaştırma, görselleştirme ve rapora hazır dışa aktarma adımlarını tek yerde bir araya getirir.

## Ne yapar?

- CSV, TXT, TSV, XLSX ve XLS gibi yaygın laboratuvar dosyalarını içe aktarır.
- Analiz öncesinde sütun eşleştirmesini ve veri kalitesi uyarılarını gözden geçirmeyi kolaylaştırır.
- Termal, spektral ve difraksiyon verileri için yönteme özel akışlar sunar.
- Çalışmaları karşılaştırmaya; figür, veri ve rapor çıktıları almaya yardımcı olur.

## Nasıl çalışır?

1. Bir veya birden fazla ölçüm dosyasını içe aktarın.
2. Algılanan dosya biçimini, sütunları ve metaveriyi kontrol edin.
3. Uygun analiz akışını seçip etkileşimli sonuçları inceleyin.
4. Gerektiğinde çalışmaları karşılaştırın; ardından veri veya raporu dışa aktarın.

MaterialScope; ham veri, işleme tercihleri, görselleştirmeler ve dışa aktarılan sonuçların aynı proje akışında bağlı kalmasını hedefler.

## Yerel kurulum

**Gereksinimler:** Python 3.11+ ve `pip`.

```bash
git clone https://github.com/utkuvibing/MaterialScope.git
cd MaterialScope
python -m venv .venv
```

Sanal ortamı etkinleştirin:

```bash
# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# macOS / Linux
source .venv/bin/activate
```

Projeyi kurup uygulamayı başlatın:

```bash
pip install -e .
python -m dash_app.server
```

Geliştirme ve test araçları için ekstra kurulum:

```bash
pip install -e ".[dev]"
```

Tarayıcıdan [http://127.0.0.1:8050](http://127.0.0.1:8050) adresini açın.

## Not

MaterialScope gelişmekte olan bir araştırma ve mühendislik projesidir. Özellikle nitel spektral ve XRD yorumlarında, analiz çıktıları uzman doğrulamasının yerini tutmaz.

## Lisans

MIT — ayrıntılar için [LICENSE](LICENSE) dosyasına bakın.
