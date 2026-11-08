"""İlk açılıştaki zevk grupları. Her grup tür ve isteğe bağlı dil eğilimine çevrilir."""

from dataclasses import dataclass


@dataclass(frozen=True)
class TasteGroup:
    id: str
    name: str
    films: str
    tags: str
    genres: tuple[str, ...]
    language: str | None = None


TASTE_GROUPS: tuple[TasteGroup, ...] = (
    TasteGroup(
        "yerli_komedi",
        "Yerli komedi",
        "Recep İvedik, G.O.R.A., Hababam Sınıfı",
        "Türk yapımı · mizah · aile",
        ("Komedi",),
        "tr",
    ),
    TasteGroup(
        "animasyon",
        "Animasyon",
        "Oyuncak Hikayesi, Şrek, Kung Fu Panda",
        "aile · macera · sıcak",
        ("Animasyon", "Aile"),
    ),
    TasteGroup(
        "fantastik",
        "Fantastik serüven",
        "Yüzüklerin Efendisi, Karayip Korsanları, Star Wars",
        "epik · dünya kurma · kahraman",
        ("Fantastik", "Macera"),
    ),
    TasteGroup(
        "aksiyon_komedi",
        "Aksiyon komedi",
        "Deadpool, Çılgın İkili, Felekten Bir Gece",
        "tempolu · alaycı · eğlenceli",
        ("Aksiyon", "Komedi"),
    ),
    TasteGroup(
        "suc_gerilim",
        "Suç ve gerilim",
        "Yedi, Esaretin Bedeli, John Wick",
        "karanlık · gerilimli · intikam",
        ("Suç", "Gerilim"),
    ),
    TasteGroup(
        "dram",
        "Duygusal dram",
        "Forrest Gump, 7. Koğuştaki Mucize, Ayla",
        "hayat hikâyesi · hüzünlü · umut",
        ("Dram",),
    ),
    TasteGroup(
        "bilim_kurgu",
        "Bilim kurgu",
        "Yıldızlararası, Matrix, Başlangıç",
        "zihin açan · gelecek · uzay",
        ("Bilim-Kurgu",),
    ),
    TasteGroup(
        "romantik",
        "Romantik",
        "Titanik, Aşk Taktikleri, Ateşten Kalbe",
        "aşk · ilişkiler · hafif",
        ("Romantik",),
    ),
    TasteGroup(
        "korku",
        "Korku ve gizem",
        "Korku Seansı, Ruhlar Bölgesi, Şeytan",
        "gerilim · doğaüstü · gizem",
        ("Korku", "Gizem"),
    ),
    TasteGroup(
        "tarih_savas",
        "Tarih ve savaş",
        "Er Ryan'ı Kurtarmak, Dunkirk, Cesur Yürek",
        "gerçek olaylar · destansı · dönem",
        ("Tarih", "Savaş"),
    ),
)

GROUPS_BY_ID = {group.id: group for group in TASTE_GROUPS}
