# ThermoAnalyzer
## Türkçe Katalog ve Kullanım Rehberi

Bu doküman, ThermoAnalyzer'in mevcut Streamlit tabanlı gösterim sürümünü hocalara, araştırmacılara ve laboratuvar kullanıcılarına tanıtmak için hazırlanmıştır. Amaç yalnızca "nasıl kullanılır?" sorusunu cevaplamak değil, aynı zamanda "neden kullanılmalı?" sorusuna da net ve ikna edici bir yanıt vermektir.

Mevcut gösterim akışı Streamlit arayüzü üzerinden çalışmaktadır. Windows masaüstü kurulum paketi ayrıca hazırlanmaktadır. Bu nedenle kısa vadeli akademik denemelerde Streamlit sürümü referans ürün kabuğu olarak kullanılacaktır.

## 1. ThermoAnalyzer nedir?

ThermoAnalyzer, DSC ve TGA odaklı, cihazdan bağımsız, tekrar üretilebilir ve proje-arşiv odaklı bir termal analiz çalışma alanıdır.

Temel hedefi şudur:

- farklı cihazlardan dışa aktarılmış termal analiz dosyalarını daha düzenli incelemek
- veri içe aktarma belirsizliklerini görünür hale getirmek
- DSC ve TGA analiz akışlarını tek bir çalışma alanında toplamak
- karşılaştırma, raporlama ve proje arşivleme süreçlerini daha kontrollü hale getirmek

Kısacası ThermoAnalyzer, yalnızca grafik gösteren bir arayüz değil; veri inceleme, analiz, karşılaştırma, çıktı alma ve proje tekrar açma zincirini tek yerde birleştiren bir akademik çalışma ortamıdır.

## 2. Neden ThermoAnalyzer kullanılmalı?

Akademik ve laboratuvar ortamlarında termal analiz verisiyle çalışırken sık görülen sorunlar vardır:

- farklı cihazların farklı dışa aktarma yapıları
- kolon adlarının tutarsız olması
- sinyal birimi veya veri tipi belirsizlikleri
- aynı verinin tekrar tekrar farklı kişilerce manuel yorumlanması
- rapor ve proje bütünlüğünün korunamaması

ThermoAnalyzer bu problemlere pratik bir cevap vermeyi amaçlar.

ThermoAnalyzer'i tercih etmek için güçlü nedenler:

- cihazdan bağımsız yaklaşım: yalnızca tek bir üreticiye bağlı kalmaz
- veri içe aktarma farkındalığı: belirsiz noktaları gizlemek yerine kullanıcıya gösterir
- DSC ve TGA için kararlı ana akış: gösterim ve kontrollü değerlendirme için en güçlü yüzey budur
- karşılaştırma alanı: birden çok koşuyu aynı bağlamda izlemeyi kolaylaştırır
- tekrar üretilebilir proje yapısı: `.thermozip` ile çalışma alanı tekrar açılabilir
- rapor ve çıktı üretimi: CSV, DOCX ve diğer çıktı yolları aynı ürün akışı içinde yer alır
- akademik deneme için uygun yapı: öğretim üyelerinin gerçek laboratuvar dışa aktarmalarıyla kontrollü değerlendirme yapmasına imkan tanır

## 3. Kimler için uygundur?

ThermoAnalyzer özellikle şu kullanıcı grupları için değerlidir:

- DSC/TGA verisiyle çalışan öğretim üyeleri
- malzeme bilimi ve polimer araştırmacıları
- lisansüstü öğrenciler
- laboratuvar sorumluları
- yöntem geliştirme veya veri tekrar gözden geçirme ihtiyacı olan ekipler

Özellikle şu durumlarda fark yaratır:

- farklı cihazlardan gelen verileri ortak bir mantıkla incelemek istediğinizde
- öğrencilerinizle standardize bir analiz akışı paylaşmak istediğinizde
- rapor, grafik ve proje dosyalarını birlikte yönetmek istediğinizde
- aynı veri setini daha sonra tekrar açıp aynı bağlamda incelemek istediğinizde

## 4. Kararlı kapsam nedir?

Bugün hocalara gösterilmesi önerilen kararlı yüzey şunlardır:

- Veri Al / Import
- Karşılaştırma Alanı
- DSC analizi
- TGA analizi
- Rapor Merkezi / dışa aktarma
- Proje kaydetme ve yeniden açma
- `.thermozip` proje arşivleri

Bu kararlı yüzey, profesör demosu ve kısa süreli akademik deneme için önerilen ana kullanım alanıdır.

## 5. Önizleme modülleri nelerdir?

Aşağıdaki alanlar ürün içinde yer alsa da kararlı ürün vaadinin parçası olarak sunulmamalıdır:

- DTA
- kinetik analiz
- pik dekonvolüsyonu

Bu modüller keşif ve değerlendirme amaçlıdır. Kısa vadeli hoca demosunda odak noktasının DSC, TGA, karşılaştırma, çıktı alma ve proje arşivi olması daha doğru olacaktır.

## 6. Ürünün temel yaklaşımı

ThermoAnalyzer'in önemli farklarından biri, veriyi "kusursuz kabul etmek" yerine "gözden geçirilmesi gereken veri" olarak ele alabilmesidir.

Bu şu anlama gelir:

- veri tipi tahmini yapılır
- sinyal ve sıcaklık kolonları otomatik algılanır
- birim ve bazı metadata alanları çıkarılmaya çalışılır
- ama belirsizlik varsa kullanıcıya uyarı verilir

Bu yaklaşım bilimsel doğruluk açısından önemlidir. Çünkü yanlış tipte içe alınmış bir verinin şık bir grafik üretmesi, onun doğru analiz edildiği anlamına gelmez. ThermoAnalyzer bu noktada kullanıcıyı daha dikkatli ve daha kontrollü bir iş akışına yönlendirmeyi amaçlar.

## 7. Streamlit gösterim sürümü nasıl çalıştırılır?

Bu bölüm, masaüstü kurulum paketi yerine şimdilik Streamlit sürümünü gösterecek kullanıcılar içindir.

Gerekli ön koşullar:

- Windows bilgisayar
- Python 3.8 veya üzeri
- internet erişimi veya hazır bağımlılık kurulumu
- proje klasörü

Kurulum adımları:

1. Proje klasörünü açın.
2. Gerekirse bir sanal ortam oluşturun.
3. Bağımlılıkları yükleyin:
   - `pip install -r requirements.txt`
4. Uygulamayı başlatın:
   - `streamlit run app.py`
5. Tarayıcıda açılan yerel adres üzerinden uygulamayı kullanın.

Beklenen açılış davranışı:

- sol tarafta ürün navigasyonu görünür
- dil seçimi yapılabilir
- ana kararlı sayfalar üst kısımda yer alır
- önizleme modülleri ayrı bir mantıkla konumlanır

## 8. Hızlı ilk gösterim akışı

Bir hocaya 5-10 dakikalık ilk gösterim yapmak isterseniz şu akış önerilir:

1. Uygulamayı açın.
2. Ana sayfada ürünün DSC/TGA odaklı kararlı kapsamını kısaca anlatın.
3. Bir DSC veya TGA örnek verisi içe aktarın.
4. İçe aktarma güveni ve uyarıları gösterin.
5. Karşılaştırma Alanı'nda seçilen veri setlerini gösterin.
6. DSC veya TGA analizini çalıştırın.
7. Sonucu kaydedin ve proje bağlamında görünür hale geldiğini gösterin.
8. CSV veya DOCX çıktısı üretin.
9. `.thermozip` proje arşivini kaydedip tekrar açma mantığını anlatın.

Bu akış, ürünün yalnızca grafik göstermediğini; veri, analiz, sonuç ve arşiv mantığını birlikte yönettiğini kısa sürede gösterir.

## 9. Sayfa sayfa kullanım rehberi

## 9.1 Veri Al / Import

Bu sayfa ürünün giriş kapısıdır.

Burada yapılabilenler:

- CSV, TXT, TSV, XLSX ve benzeri dosyaları yüklemek
- veri tipi tahminini görmek
- kolon eşleşmelerini kontrol etmek
- sinyal ve sıcaklık alanlarını incelemek
- import güveni ve review uyarılarını değerlendirmek
- veri setini çalışma alanına eklemek

Bu sayfada özellikle dikkat edilmesi gerekenler:

- veri tipi gerçekten DSC mi, TGA mı?
- sıcaklık kolonu doğru algılandı mı?
- sinyal kolonu doğru mu?
- birim bilgisi doğru mu?
- kullanıcıdan inceleme isteyen bir uyarı var mı?

Ürünün en güçlü yanlarından biri bu aşamada ortaya çıkar: belirsiz veriyi sessizce kabul etmek yerine kullanıcıyı uyarır.

## 9.2 Karşılaştırma Alanı

Karşılaştırma Alanı, birden fazla koşuyu birlikte değerlendirmek için kullanılır.

Burada yapılabilenler:

- veri setlerini seçmek
- seçili koşuları birlikte görmek
- karşılaştırma notları tutmak
- uygun veri setleri üzerinde ortak analiz şablonu düşünmek
- batch yönüne hazırlık yapmak

Bu sayfa şu nedenle önemlidir:

- tek koşu analizi yerine laboratuvar mantığına daha yakın bir çalışma düzeni sunar
- tekrar ölçümlerini, benzer koşuları veya karşılaştırmalı incelemeleri daha rahat hale getirir

## 9.3 DSC Analizi

DSC sayfası, seçili veri seti üzerinde kararlı DSC iş akışını yürütmek için kullanılır.

Burada görülen ana mantık:

- aktif veri seti bağlamı
- doğrulama durumu
- işleme veya yöntem bağlamı
- sonuç özeti

DSC gösteriminde vurgulanabilecek noktalar:

- veri seti bağlamının analizle birlikte korunması
- doğrulama ve uyarı bilgilerinin görünür olması
- sonuçların yalnızca anlık değil, kayıtlı proje mantığıyla saklanabilmesi

## 9.4 TGA Analizi

TGA sayfası, seçili veri seti üzerinde kararlı TGA akışını yürütmek için kullanılır.

Burada özellikle şu noktalar değerlidir:

- aktif veri seti ve birim bağlamı
- import review ve validation görünürlüğü
- sonuçların proje yapısına eklenmesi

TGA tarafında öğretim üyelerine özellikle gösterilebilecek şey:

- veri içe aktarma belirsizliklerinin sonuca bağlanmadan önce görünür tutulması

## 9.5 Rapor Merkezi / Export

Bu alan, analiz sonuçlarının dışa aktarım ve raporlama yüzeyidir.

Burada yapılabilenler:

- kayıtlı sonuçlar arasından seçim yapmak
- dışa aktarma bağlamını hazırlamak
- CSV üretmek
- DOCX raporu üretmek

Bu sayfa özellikle akademik kullanımda önemlidir çünkü:

- elde edilen sonucun yalnızca ekranda kalmamasını sağlar
- paylaşılabilir ve arşivlenebilir çıktı üretir
- rapor ve analiz bağlamını daha düzenli hale getirir

## 9.6 Proje Alanı

Proje Alanı, çalışma alanının bütünlüğünü gösterir.

Burada görülebilenler:

- veri seti sayısı
- kayıtlı sonuç sayısı
- geçmiş veya bağlam bilgisi
- seçili sonuç detayları

Bu alanın önemli değeri şudur:

- kullanıcı yalnızca tek anlık analiz değil, bütün bir çalışma alanı mantığıyla çalışır

## 9.7 Lisans / Hakkında

Bu alan, ürünün kapsamını ve odak alanını anlatmak için kullanılır.

Özellikle profesör demosunda burada şu mesaj net verilmelidir:

- ürünün kararlı odak alanı DSC ve TGA'dır
- karşılaştırma, proje arşivi ve raporlama desteklenir
- önizleme modülleri keşif amaçlıdır

## 10. 1 günlük hoca denemesi için önerilen senaryo

Bir günlük denemede kullanıcılardan şunları istemek mantıklıdır:

- en az bir gerçek DSC verisi içe aktarmaları
- en az bir gerçek TGA verisi içe aktarmaları
- import güveni ve uyarı mantığını kontrol etmeleri
- birkaç veri setini Karşılaştırma Alanı'nda birlikte incelemeleri
- en az bir DSC veya TGA sonucu üretmeleri
- CSV veya DOCX çıktısı almaları
- `.thermozip` kaydedip tekrar açmaları

Bu denemeden alınacak en değerli geri bildirimler:

- içe aktarma hataları
- yanlış veri tipi tahmini
- yanlış sinyal veya kolon algılama
- rapor içeriğinde eksik bağlam
- kaydedilen projenin tekrar açıldığında beklenen durumu koruyup korumadığı

## 11. Desteklenen ve önerilen dosya türleri

En uygun dosya türleri:

- CSV
- TXT
- TSV
- XLSX
- XLS

En güvenilir senaryolar:

- başlıkları net olan ayrılmış metin dosyaları
- TA benzeri metin dışa aktarmaları
- NETZSCH benzeri metin dışa aktarmaları

Temkinli yaklaşılması gereken durumlar:

- kolon adı eksik veya çok belirsiz dosyalar
- sonradan elle düzenlenmiş dışa aktarmalar
- birim bilgisinin kaldırıldığı dosyalar
- proprietary binary formatlar

## 12. Ürünün güçlü yönleri

ThermoAnalyzer'i benzer akademik araçlardan ayıran pratik yönler:

- yalnızca analiz değil, iş akışı odaklıdır
- yalnızca grafik değil, bağlam da üretir
- yalnızca sonuç değil, proje arşivi de sunar
- yalnızca tek veri değil, karşılaştırma mantığı da vardır
- yalnızca içe aktarma değil, review ve validation görünürlüğü de vardır

Bu nedenle ürün:

- araştırma grubunda ortak kullanım
- tez öğrencisi eğitimi
- laboratuvar dersi gösterimi
- veri tekrar inceleme
- çıktı ve proje bütünlüğü

için anlamlı bir temel sunar.

## 13. Şimdilik neden Streamlit sürümü gösteriliyor?

Kısa cevap:

- çünkü mevcut referans ürün kabuğu Streamlit tarafındadır
- ürünün tam ve oturmuş iş akışı bugün en net şekilde burada görünür
- Windows masaüstü paketleme hattı ayrıca hazırlanmaktadır

Bu nedenle kısa vadeli öğretim üyesi demosunda Streamlit sürümünü göstermek teknik olarak mantıklıdır. Ürünün gerçek kullanıcı akışı burada daha olgun ve daha kapsamlı görünür.

## 14. Yakın vadede beklenen yön

Yakın vadede hedeflenen yön:

- profesörlerin doğrudan indirebileceği Windows masaüstü kurulum paketi
- daha kolay ilk kullanım deneyimi
- sistem Python bağımlılığı olmadan açılabilen masaüstü sürüm

Ancak bugün için değerlendirme yapılırken ürünün bilimsel ve iş akışı değeri Streamlit sürümü üzerinden rahatlıkla gösterilebilir.

## 15. Demo sırasında söylenebilecek kısa ürün mesajı

ThermoAnalyzer, termal analiz verisini yalnızca görüntüleyen değil; içe aktaran, sorgulayan, analiz eden, karşılaştıran, raporlayan ve tekrar açılabilir proje halinde saklayan bütünleşik bir akademik çalışma alanıdır.

## 16. Sık sorulan sorular

### Bu ürün hangi analizlerde en güvenilir?

Bugünkü kararlı gösterim kapsamında en güvenilir yüzey DSC, TGA, Karşılaştırma Alanı, çıktı üretimi ve proje arşividir.

### Kinetik veya DTA kullanılamıyor mu?

Kullanılabilir, ancak bunlar şu aşamada önizleme niteliğindedir. Kısa vadeli profesör demosunda kararlı ürün vaadi içinde sunulmamalıdır.

### Masaüstü sürüm ne zaman kullanılacak?

Windows masaüstü sürümü hazırlanmaktadır. Şimdilik en doğru referans ürün deneyimi Streamlit arayüzüdür.

### Bu ürün neden faydalı olabilir?

Çünkü veri içe aktarmadan rapora kadar aynı bağlamı koruyan, cihazdan bağımsız ve proje tekrar açmaya uygun bir akademik termal analiz akışı sunar.

## 17. Sonuç

ThermoAnalyzer, kısa vadede özellikle şu soruna güçlü cevap verir:

"Laboratuvardan dışa aktarılan DSC/TGA verilerini daha düzenli, daha görünür, daha tekrar üretilebilir ve daha paylaşılabilir bir iş akışı içinde nasıl ele alabiliriz?"

Eğer hedefiniz:

- öğrencilere daha düzenli bir analiz akışı göstermek
- gerçek laboratuvar verilerini tek bir yüzeyde değerlendirmek
- çıktıları ve proje durumunu bir arada yönetmek
- DSC ve TGA odaklı bir akademik yazılımı erken aşamada değerlendirmek

ise ThermoAnalyzer güçlü ve anlamlı bir adaydır.

## 18. Kısa kapanış metni

ThermoAnalyzer, termal analizde yalnızca sonuç üretmeyi değil, veriyi güvenle yorumlamayı ve aynı çalışmayı tekrar açılabilir bir bağlam içinde sürdürebilmeyi hedefler. Bu yüzden özellikle öğretim, araştırma ve kontrollü akademik değerlendirme için dikkat çekici bir araçtır.
