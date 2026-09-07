import asyncio
import glob
import os
import re
import traceback
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client
from telegram import Bot
from yt_dlp import YoutubeDL


# ============================================================
# 1. Environment Variables
# ============================================================

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")

# يفضل استخدام Service Role في Backend / GitHub Actions
# وسيتم الرجوع إلى ANON_KEY إذا لم يكن Service Role موجودًا.
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or os.getenv(
    "SUPABASE_ANON_KEY"
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


if not all(
    [
        SUPABASE_URL,
        SUPABASE_KEY,
        TELEGRAM_BOT_TOKEN,
        TELEGRAM_CHAT_ID,
    ]
):
    raise ValueError(
        "❌ خطأ: بعض Environment Variables مفقودة!\n\n"
        "المطلوب:\n"
        "SUPABASE_URL\n"
        "SUPABASE_SERVICE_ROLE_KEY أو SUPABASE_ANON_KEY\n"
        "TELEGRAM_BOT_TOKEN\n"
        "TELEGRAM_CHAT_ID"
    )


supabase: Client = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
)


# ============================================================
# 2. إعدادات التحميل
# ============================================================

# عدد نتائج البحث التي سيتم تجربتها
SEARCH_RESULTS = 5

# أقصى مدة للفيديو بالثواني.
# None = بدون حد.
MAX_VIDEO_DURATION = 60 * 30  # 30 دقيقة

# أقل مدة مقبولة.
MIN_VIDEO_DURATION = 20

# الحد الأقصى المقترح للجودة
MAX_HEIGHT = 1080


# ============================================================
# 3. قصص القرآن
# ============================================================

STORIES_MAPPING = [
    {
        "story_title": "قصة أصحاب الكهف",
        "surah_number": 18,
        "start_ayah": 9,
        "end_ayah": 26,
        "search_query": "قصة أصحاب الكهف ملخصة",
    },
    {
        "story_title": "قصة صاحب الجنتين",
        "surah_number": 18,
        "start_ayah": 32,
        "end_ayah": 44,
        "search_query": "قصة صاحب الجنتين سورة الكهف",
    },
    {
        "story_title": "قصة موسى والخضر",
        "surah_number": 18,
        "start_ayah": 60,
        "end_ayah": 82,
        "search_query": "قصة موسى والخضر سورة الكهف",
    },
    {
        "story_title": "قصة ذو القرنين",
        "surah_number": 18,
        "start_ayah": 83,
        "end_ayah": 98,
        "search_query": "قصة ذو القرنين سورة الكهف",
    },
]


# ============================================================
# 4. تنظيف أسماء الملفات
# ============================================================

def safe_filename(value: str) -> str:
    """
    تحويل النص إلى اسم ملف آمن.
    """

    value = re.sub(
        r'[<>:"/\\|?*]',
        "_",
        value,
    )

    value = re.sub(
        r"\s+",
        "_",
        value,
    )

    return value[:100]


# ============================================================
# 5. تنظيف الملفات المؤقتة
# ============================================================

def cleanup_temp_files(base_name: str) -> None:
    """
    حذف الملفات المؤقتة الناتجة عن yt-dlp.
    """

    patterns = [
        f"{base_name}.*",
    ]

    for pattern in patterns:

        for file_path in glob.glob(pattern):

            try:

                if os.path.isfile(file_path):

                    os.remove(file_path)

                    print(
                        f"🧹 تم حذف الملف: "
                        f"{file_path}"
                    )

            except Exception as e:

                print(
                    f"⚠️ تعذر حذف "
                    f"{file_path}: {e}"
                )


# ============================================================
# 6. العثور على الفيديو النهائي
# ============================================================

def find_downloaded_video(
    base_name: str,
) -> Optional[str]:

    allowed_extensions = {
        ".mp4",
        ".mkv",
        ".webm",
        ".mov",
        ".avi",
    }

    ignored_extensions = {
        ".part",
        ".ytdl",
        ".tmp",
    }

    files = glob.glob(
        f"{base_name}.*"
    )

    valid_files = []

    for file_path in files:

        if not os.path.isfile(file_path):
            continue

        extension = (
            os.path.splitext(
                file_path
            )[1]
            .lower()
        )

        if extension in ignored_extensions:
            continue

        if extension not in allowed_extensions:
            continue

        try:

            size = os.path.getsize(
                file_path
            )

            if size <= 0:
                continue

        except OSError:

            continue

        valid_files.append(
            file_path
        )

    if not valid_files:
        return None

    # الأكبر غالبًا هو الملف النهائي
    valid_files.sort(
        key=lambda path: os.path.getsize(path),
        reverse=True,
    )

    return valid_files[0]


# ============================================================
# 7. تقييم نتائج YouTube
# ============================================================

def score_video(
    video: dict,
    query: str,
) -> int:

    title = (
        video.get("title")
        or ""
    ).lower()

    score = 0

    # --------------------------------------------------------
    # كلمات البحث
    # --------------------------------------------------------

    query_words = [
        word.strip().lower()
        for word in query.split()
        if len(word.strip()) >= 3
    ]

    for word in query_words:

        if word in title:

            score += 10

    # --------------------------------------------------------
    # كلمات مرغوبة
    # --------------------------------------------------------

    preferred_words = [
        "قصة",
        "القرآن",
        "سورة",
        "اسلام",
        "إسلام",
        "قصص",
        "عبرة",
        "عبر",
        "قصص القرآن",
    ]

    for word in preferred_words:

        if word.lower() in title:

            score += 5

    # --------------------------------------------------------
    # كلمات غير مرغوبة
    # --------------------------------------------------------

    unwanted_words = [
        "shorts",
        "short",
        "تيك توك",
        "tiktok",
        "ريلز",
        "reels",
        "reaction",
        "رد فعل",
        "موسيقى",
        "اغنية",
        "أغنية",
    ]

    for word in unwanted_words:

        if word in title:

            score -= 30

    # --------------------------------------------------------
    # مدة الفيديو
    # --------------------------------------------------------

    duration = video.get(
        "duration"
    )

    if duration:

        if (
            MIN_VIDEO_DURATION
            <= duration
            <= MAX_VIDEO_DURATION
        ):

            score += 15

        elif duration < MIN_VIDEO_DURATION:

            score -= 20

        elif duration > MAX_VIDEO_DURATION:

            score -= 20

    # --------------------------------------------------------
    # عدد المشاهدات
    # --------------------------------------------------------

    view_count = video.get(
        "view_count"
    )

    if view_count:

        if view_count >= 1_000_000:
            score += 15

        elif view_count >= 100_000:
            score += 10

        elif view_count >= 10_000:
            score += 5

    # --------------------------------------------------------
    # تقييم القناة
    # --------------------------------------------------------

    channel = (
        video.get("channel")
        or video.get("uploader")
        or ""
    ).lower()

    if any(
        word in channel
        for word in [
            "قرآن",
            "القران",
            "quran",
            "اسلام",
            "islam",
        ]
    ):

        score += 5

    return score


# ============================================================
# 8. البحث عن أفضل فيديو
# ============================================================

def search_best_youtube_video(
    query: str,
) -> Optional[dict]:

    print()
    print(
        f"🔎 البحث عن أفضل فيديو:"
    )
    print(
        f"   {query}"
    )

    search_query = (
        f"ytsearch{SEARCH_RESULTS}:"
        f"{query}"
    )

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,

        "extract_flat": True,

        "skip_download": True,

        "retries": 3,
    }

    cookies_file = "cookies.txt"

    if os.path.exists(
        cookies_file
    ):

        ydl_opts["cookiefile"] = (
            cookies_file
        )

    try:

        with YoutubeDL(
            ydl_opts
        ) as ydl:

            result = ydl.extract_info(
                search_query,
                download=False,
            )

        if not result:

            print(
                "❌ لم يتم الحصول "
                "على نتائج."
            )

            return None

        entries = (
            result.get("entries")
            or []
        )

        if not entries:

            print(
                "❌ لا توجد نتائج."
            )

            return None

        candidates = []

        print()
        print(
            f"📋 تم العثور على "
            f"{len(entries)} نتائج:"
        )

        for index, video in enumerate(
            entries,
            start=1,
        ):

            if not video:
                continue

            title = (
                video.get("title")
                or "بدون عنوان"
            )

            duration = (
                video.get("duration")
                or 0
            )

            views = (
                video.get("view_count")
                or 0
            )

            score = score_video(
                video,
                query,
            )

            print()
            print(
                f"{index}. {title}"
            )
            print(
                f"   ⏱️ {duration} ثانية"
            )
            print(
                f"   👁️ {views:,} مشاهدة"
            )
            print(
                f"   ⭐ Score: {score}"
            )

            candidates.append(
                (
                    score,
                    video,
                )
            )

        if not candidates:

            return None

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        best_score, best_video = (
            candidates[0]
        )

        print()
        print(
            "🏆 أفضل نتيجة:"
        )
        print(
            f"   {best_video.get('title')}"
        )
        print(
            f"⭐ Score: {best_score}"
        )

        return best_video

    except Exception as e:

        print(
            f"❌ خطأ أثناء البحث:"
            f"\n{e}"
        )

        traceback.print_exc()

        return None


# ============================================================
# 9. تحميل الفيديو
# ============================================================

def download_youtube_video(
    video: dict,
    output_filename: str,
) -> Optional[str]:

    base_name = os.path.splitext(
        output_filename
    )[0]

    cleanup_temp_files(
        base_name
    )

    video_url = (
        video.get("webpage_url")
        or video.get("url")
    )

    if not video_url:

        video_id = video.get(
            "id"
        )

        if video_id:

            video_url = (
                f"https://www.youtube.com/watch?v="
                f"{video_id}"
            )

    if not video_url:

        print(
            "❌ لم يتم العثور على "
            "رابط الفيديو."
        )

        return None

    print()
    print(
        "⬇️ بدء تحميل الفيديو:"
    )
    print(
        f"🔗 {video_url}"
    )

    output_template = (
        f"{base_name}.%(ext)s"
    )

    ydl_opts = {

        # ----------------------------------------------------
        # Format مرن
        # ----------------------------------------------------
        "format": (
            f"bv*[height<={MAX_HEIGHT}]"
            "+ba/"
            f"b[height<={MAX_HEIGHT}]/"
            "b"
        ),

        # محاولة الدمج إلى MP4
        "merge_output_format": "mp4",

        "outtmpl": output_template,

        "noplaylist": True,

        "quiet": False,

        "no_warnings": False,

        # ----------------------------------------------------
        # Retry
        # ----------------------------------------------------
        "retries": 5,

        "fragment_retries": 5,

        "file_access_retries": 3,

        "retry_sleep_functions": {
            "http": lambda n: min(
                5 * (n + 1),
                30,
            ),
        },

        "skip_unavailable_fragments": True,

        # ----------------------------------------------------
        # Headers
        # ----------------------------------------------------
        "http_headers": {
            "Accept-Language": (
                "ar,en;q=0.8"
            ),
        },

        # ----------------------------------------------------
        # SSL طبيعي
        # ----------------------------------------------------
        "nocheckcertificate": False,

        # ----------------------------------------------------
        # Geo bypass
        # ----------------------------------------------------
        "geo_bypass": True,
    }

    cookies_file = "cookies.txt"

    if os.path.exists(
        cookies_file
    ):

        ydl_opts["cookiefile"] = (
            cookies_file
        )

    try:

        with YoutubeDL(
            ydl_opts
        ) as ydl:

            ydl.download(
                [
                    video_url
                ]
            )

        actual_file = (
            find_downloaded_video(
                base_name
            )
        )

        if not actual_file:

            print(
                "❌ انتهى yt-dlp "
                "ولكن الملف غير موجود."
            )

            return None

        file_size = os.path.getsize(
            actual_file
        )

        if file_size <= 0:

            print(
                "❌ ملف الفيديو فارغ."
            )

            return None

        size_mb = (
            file_size
            / (1024 * 1024)
        )

        print()
        print(
            "✅ تم تحميل الفيديو!"
        )
        print(
            f"📁 {actual_file}"
        )
        print(
            f"📦 الحجم: {size_mb:.2f} MB"
        )

        return actual_file

    except Exception as e:

        print()
        print(
            "❌ فشل تحميل الفيديو:"
        )
        print(e)

        traceback.print_exc()

        cleanup_temp_files(
            base_name
        )

        return None


# ============================================================
# 10. البحث + التحميل
# ============================================================

def search_and_download_youtube(
    query: str,
    output_filename: str,
) -> Optional[str]:

    # --------------------------------------------------------
    # البحث عن أفضل نتيجة
    # --------------------------------------------------------

    best_video = (
        search_best_youtube_video(
            query
        )
    )

    if not best_video:

        return None

    # --------------------------------------------------------
    # تحميل النتيجة الأفضل
    # --------------------------------------------------------

    downloaded = (
        download_youtube_video(
            best_video,
            output_filename,
        )
    )

    if downloaded:

        return downloaded

    # --------------------------------------------------------
    # إذا فشل التحميل، نحاول نتائج أخرى
    # --------------------------------------------------------

    print()
    print(
        "⚠️ فشل تحميل أفضل نتيجة."
    )
    print(
        "🔄 سيتم محاولة نتائج أخرى..."
    )

    search_query = (
        f"ytsearch{SEARCH_RESULTS}:"
        f"{query}"
    )

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extract_flat": True,
        "skip_download": True,
    }

    try:

        with YoutubeDL(
            ydl_opts
        ) as ydl:

            result = ydl.extract_info(
                search_query,
                download=False,
            )

        entries = (
            result.get("entries")
            or []
        )

        candidates = []

        for video in entries:

            if not video:
                continue

            score = score_video(
                video,
                query,
            )

            candidates.append(
                (
                    score,
                    video,
                )
            )

        candidates.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        for index, (
            score,
            video,
        ) in enumerate(
            candidates,
            start=1,
        ):

            # تخطي النتيجة التي جربناها أولًا
            if index == 1:
                continue

            print()
            print(
                f"🔄 محاولة فيديو بديل "
                f"{index}:"
            )
            print(
                f"🎬 {video.get('title')}"
            )

            downloaded = (
                download_youtube_video(
                    video,
                    output_filename,
                )
            )

            if downloaded:

                return downloaded

    except Exception as e:

        print(
            f"❌ خطأ أثناء تجربة "
            f"النتائج البديلة: {e}"
        )

        traceback.print_exc()

    return None


# ============================================================
# 11. رفع Telegram
# ============================================================

async def upload_to_telegram(
    bot: Bot,
    file_path: str,
    caption: str,
) -> Optional[str]:

    print()
    print(
        "📤 جاري رفع الفيديو إلى Telegram..."
    )

    try:

        with open(
            file_path,
            "rb",
        ) as video_file:

            message = await bot.send_video(
                chat_id=TELEGRAM_CHAT_ID,
                video=video_file,
                caption=caption,
                supports_streaming=True,
            )

        if not message.video:

            print(
                "❌ Telegram لم يرجع "
                "بيانات الفيديو."
            )

            return None

        file_id = (
            message.video.file_id
        )

        file_unique_id = (
            message.video.file_unique_id
        )

        print()
        print(
            "🎉 تم رفع الفيديو بنجاح!"
        )
        print(
            f"🆔 file_id: {file_id}"
        )
        print(
            f"🔐 file_unique_id: "
            f"{file_unique_id}"
        )

        return file_id

    except Exception as e:

        print()
        print(
            "❌ فشل رفع الفيديو إلى Telegram:"
        )
        print(e)

        traceback.print_exc()

        return None


# ============================================================
# 12. الحصول على Surah ID
# ============================================================

def get_surah_id(
    surah_number: int,
) -> Optional[str]:

    try:

        response = (
            supabase
            .from_("surahs")
            .select("id")
            .eq(
                "surah_number",
                surah_number,
            )
            .single()
            .execute()
        )

        if not response.data:

            print(
                f"❌ لم يتم العثور على "
                f"السورة رقم {surah_number}"
            )

            return None

        return response.data["id"]

    except Exception as e:

        print(
            f"❌ خطأ في جلب السورة "
            f"{surah_number}: {e}"
        )

        traceback.print_exc()

        return None


# ============================================================
# 13. الحصول على الآيات
# ============================================================

def get_ayahs(
    surah_id: str,
    start_ayah: int,
    end_ayah: int,
):

    try:

        response = (
            supabase
            .from_("ayahs")
            .select(
                "id,number_in_surah"
            )
            .eq(
                "surah_id",
                surah_id,
            )
            .gte(
                "number_in_surah",
                start_ayah,
            )
            .lte(
                "number_in_surah",
                end_ayah,
            )
            .order(
                "number_in_surah",
                desc=False,
            )
            .execute()
        )

        return response.data or []

    except Exception as e:

        print(
            "❌ خطأ أثناء جلب الآيات:"
        )
        print(e)

        traceback.print_exc()

        return []


# ============================================================
# 14. التحقق من وجود القصة
# ============================================================

def story_already_exists(
    surah_number: int,
    start_ayah: int,
    end_ayah: int,
) -> bool:

    try:

        surah_id = get_surah_id(
            surah_number
        )

        if not surah_id:

            return False

        ayahs = get_ayahs(
            surah_id,
            start_ayah,
            end_ayah,
        )

        if not ayahs:

            return False

        ayah_ids = [
            ayah["id"]
            for ayah in ayahs
        ]

        response = (
            supabase
            .from_("ayahs_stories")
            .select(
                "id,ayah_id,telegram_file_id"
            )
            .in_(
                "ayah_id",
                ayah_ids,
            )
            .execute()
        )

        records = (
            response.data or []
        )

        # يجب أن تكون كل الآيات موجودة
        if len(records) != len(
            ayahs
        ):

            return False

        # وكلها يجب أن تحتوي على Telegram file_id
        for record in records:

            if not record.get(
                "telegram_file_id"
            ):

                return False

        print(
            "⏭️ القصة موجودة بالفعل "
            "بشكل كامل."
        )

        return True

    except Exception as e:

        print(
            f"⚠️ تعذر التحقق من القصة: "
            f"{e}"
        )

        return False


# ============================================================
# 15. ربط القصة بالآيات
# ============================================================

def link_story_to_supabase(
    surah_number: int,
    start_ayah: int,
    end_ayah: int,
    story_title: str,
    telegram_file_id: str,
) -> bool:

    print()
    print(
        f"🔗 ربط '{story_title}' "
        f"بالآيات "
        f"{start_ayah}-{end_ayah}"
    )

    # --------------------------------------------------------
    # الحصول على السورة
    # --------------------------------------------------------

    surah_id = get_surah_id(
        surah_number
    )

    if not surah_id:

        return False

    # --------------------------------------------------------
    # الحصول على الآيات
    # --------------------------------------------------------

    ayahs = get_ayahs(
        surah_id,
        start_ayah,
        end_ayah,
    )

    if not ayahs:

        print(
            "❌ لم يتم العثور على الآيات."
        )

        return False

    print(
        f"📌 عدد الآيات: "
        f"{len(ayahs)}"
    )

    success_count = 0

    # --------------------------------------------------------
    # تحديث أو إضافة كل آية
    # --------------------------------------------------------

    for ayah in ayahs:

        ayah_id = ayah["id"]

        number_in_surah = (
            ayah["number_in_surah"]
        )

        try:

            existing = (
                supabase
                .from_("ayahs_stories")
                .select("id")
                .eq(
                    "ayah_id",
                    ayah_id,
                )
                .limit(1)
                .execute()
            )

            records = (
                existing.data or []
            )

            data = {
                "ayah_id": ayah_id,

                "title": story_title,

                "content": (
                    f"فيديو قصة "
                    f"{story_title}"
                ),

                "source": "YouTube",

                "telegram_file_id": (
                    telegram_file_id
                ),
            }

            # ------------------------------------------------
            # تحديث سجل موجود
            # ------------------------------------------------

            if records:

                story_id = records[0][
                    "id"
                ]

                (
                    supabase
                    .from_("ayahs_stories")
                    .update(data)
                    .eq(
                        "id",
                        story_id,
                    )
                    .execute()
                )

                print(
                    f"🔄 الآية "
                    f"{number_in_surah} "
                    f"تم تحديثها."
                )

            # ------------------------------------------------
            # إضافة سجل جديد
            # ------------------------------------------------

            else:

                (
                    supabase
                    .from_("ayahs_stories")
                    .insert(data)
                    .execute()
                )

                print(
                    f"➕ الآية "
                    f"{number_in_surah} "
                    f"تمت إضافتها."
                )

            success_count += 1

        except Exception as e:

            print(
                f"❌ خطأ في الآية "
                f"{number_in_surah}:"
            )

            print(e)

            traceback.print_exc()

    print()
    print(
        f"📊 النتيجة: "
        f"{success_count}/"
        f"{len(ayahs)}"
    )

    return (
        success_count
        == len(ayahs)
    )


# ============================================================
# 16. معالجة قصة واحدة
# ============================================================

async def process_story(
    bot: Bot,
    story: dict,
):

    story_title = story[
        "story_title"
    ]

    surah_number = story[
        "surah_number"
    ]

    start_ayah = story[
        "start_ayah"
    ]

    end_ayah = story[
        "end_ayah"
    ]

    print()
    print("=" * 60)
    print(
        f"🚀 بدء معالجة: "
        f"{story_title}"
    )
    print("=" * 60)

    # --------------------------------------------------------
    # منع إعادة معالجة القصة
    # --------------------------------------------------------

    if story_already_exists(
        surah_number,
        start_ayah,
        end_ayah,
    ):

        print(
            f"⏭️ تم تخطي "
            f"'{story_title}'"
        )

        return

    # --------------------------------------------------------
    # اسم ملف آمن
    # --------------------------------------------------------

    base_name = safe_filename(
        f"temp_story_"
        f"{surah_number}_"
        f"{start_ayah}_"
        f"{end_ayah}"
    )

    output_filename = (
        f"{base_name}.mp4"
    )

    downloaded_file = None

    try:

        # ----------------------------------------------------
        # البحث والتحميل
        # ----------------------------------------------------

        downloaded_file = (
            search_and_download_youtube(
                story["search_query"],
                output_filename,
            )
        )

        if not downloaded_file:

            print(
                f"❌ فشل تحميل "
                f"'{story_title}'"
            )

            return

        if not os.path.exists(
            downloaded_file
        ):

            print(
                "❌ الملف غير موجود."
            )

            return

        # ----------------------------------------------------
        # Telegram
        # ----------------------------------------------------

        file_id = (
            await upload_to_telegram(
                bot,
                downloaded_file,
                f"📖 {story_title}",
            )
        )

        if not file_id:

            print(
                "❌ فشل رفع الفيديو."
            )

            return

        # ----------------------------------------------------
        # Supabase
        # ----------------------------------------------------

        success = (
            link_story_to_supabase(
                surah_number=surah_number,
                start_ayah=start_ayah,
                end_ayah=end_ayah,
                story_title=story_title,
                telegram_file_id=file_id,
            )
        )

        if success:

            print()
            print(
                "🎉 تم الانتهاء بنجاح!"
            )
            print(
                f"📖 {story_title}"
            )

        else:

            print()
            print(
                "⚠️ Telegram نجح، "
                "لكن ربط Supabase لم يكتمل."
            )

            print(
                "🆔 احتفظ بهذا file_id:"
            )
            print(file_id)

    except Exception as e:

        print()
        print(
            f"❌ خطأ غير متوقع "
            f"في '{story_title}':"
        )

        print(e)

        traceback.print_exc()

    finally:

        # ----------------------------------------------------
        # تنظيف الملفات دائمًا
        # ----------------------------------------------------

        cleanup_temp_files(
            base_name
        )


# ============================================================
# 17. Main
# ============================================================

async def main():

    print()
    print("=" * 60)
    print(
        "📖 Quran Stories Processor"
    )
    print("=" * 60)

    bot = Bot(
        token=TELEGRAM_BOT_TOKEN
    )

    try:

        for story in STORIES_MAPPING:

            await process_story(
                bot,
                story,
            )

    finally:

        try:

            await bot.shutdown()

        except Exception:

            pass

    print()
    print("=" * 60)
    print(
        "🎉 تم إنهاء جميع العمليات!"
    )
    print("=" * 60)


# ============================================================
# 18. Entry Point
# ============================================================

if __name__ == "__main__":

    asyncio.run(
        main()
    )
