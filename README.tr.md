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

Bu komut, Dash arayüzünü ve FastAPI API'sini aynı portta sunan tek bir süreç başlatır. Dash için ikinci bir arka uç başlatmanız gerekmez.

Örnek verilerle deneme adımları ve geri bildirim yönergeleri için [erken test rehberine](docs/early-tester-guide.md) bakın (İngilizce).

## Veri ve çalıştırma modeli

Yerel başlatmada uygulama bilgisayarınızda çalışır. Çalışma alanları bellekte tutulur: sunucuyu durdurmadan veya yeniden başlatmadan önce Proje sayfasından bir `.scopezip` proje arşivi indirip diskte saklayın. Analiz sonucunu çalışma alanına kaydetmek kalıcı yedek oluşturmaz. Daha sonra devam etmek için arşivi Proje sayfasından açın; özgün ölçüm dosyalarınızı ayrıca saklayın.

Yerel kullanım önceliği, her özelliğin çevrimdışı olduğu anlamına gelmez. Yapılandırılmış referans kütüphanesi indirmeleri, bulut kütüphanesi sorguları ve literatür hizmetleri ağ istekleri yapabilir. Bu akışlar için [referans kütüphanesi yapılandırmasına](docs/reference_library_ingest.md) bakın.

API kimlik doğrulaması isteğe bağlıdır. Korumalı API uç noktalarında etkinleştirmek için birleşik sunucuyu kendi anahtarınızla başlatın:

```bash
python -m dash_app.server --token "YOUR_PRIVATE_TOKEN"
```

Birlikte çalışan Dash istemcisi bu anahtarı otomatik alır. Yalnızca `MATERIALSCOPE_API_TOKEN` ayarlamak istemciyi yapılandırır; sunucuda kimlik doğrulamasını etkinleştirmez. Loopback dışındaki bir adrese anahtarsız bağlanmak uyarı verir, ancak sunucu yine başlar. Anahtar etkin olsa bile `/health` kimlik doğrulaması istemez. Bu API anahtarı bir tarayıcı oturum açma sistemi değildir.

## Diğer uygulama arayüzleri

[Windows kurulum paketi](packaging/windows/README.md), Streamlit uygulamasını korur ve öncelikle 8501 portunu kullanır. [Electron kabuğu](desktop/electron/README.md), yalnızca arka uç hizmetini başlatan deneysel bir masaüstü çalışmasıdır; Dash arayüzünü paketlemez.

Streamlit'teki kütüphane, lisans, kinetik analiz ve dekonvolüsyon sayfalarının Dash'te eşdeğer sayfaları yoktur; kinetik analiz ve dekonvolüsyon önizleme özellikleridir. Dash kütüphane özellikleri ve arka uç uç noktaları, sayfaların eşdeğer olduğu anlamına gelmez. Ortak çeviriler de dahil olmak üzere Streamlit bağımlılığı sürmektedir. Eksikler ve geçiş önkoşulları için [Streamlit eşdeğerlik envanterine](docs/streamlit-parity-inventory.md) bakın. Kullanımdan kaldırma ayrı bir geçiş çalışması gerektirir; tarih belirlenmemiştir.

Güncel belgelerde MaterialScope adı kullanılır. Mevcut `ThermoAnalyzer` paketleme dosya adları, ortam değişkeni takma adları ve diğer uyumluluk tanımlayıcıları korunur.

## Not

MaterialScope gelişmekte olan bir araştırma ve mühendislik projesidir. Özellikle nitel spektral ve XRD yorumlarında, analiz çıktıları uzman doğrulamasının yerini tutmaz.

## Lisans

MIT — ayrıntılar için [LICENSE](LICENSE) dosyasına bakın.

İsteğe bağlı ticari lisans denetimi API anahtarından ayrıdır. HMAC demo sırrı herkese açıktır; bu sırrı bilen herkes lisans anahtarı üretebilir. Ticari kurulumlarda `MATERIALSCOPE_LICENSE_SECRET` dışarıdan sağlanmalıdır; sırrın değiştirilmesi mevcut imzalı lisansları geçersiz kılar ve yeniden düzenlenmelerini gerektirir. İstemcide tutulan ortak bir sır, dağıtılan uygulamalar için yine de güvenli lisanslama sağlayamaz. Asimetrik imzalama sonraki bir çalışmadır.
