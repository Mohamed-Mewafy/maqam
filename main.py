import asyncio
import glob
import os
import traceback
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client
from telegram import Bot
from yt_dlp import YoutubeDL


# ============================================================
# 1. تحميل Environment Variables
# ============================================================

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
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
        "❌ خطأ: بعض المتغيرات البيئية مفقودة!\n"
        "تأكد من وجود:\n"
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
# 2. قصص القرآن ونطاق الآيات
# ============================================================

STORIES_MAPPING = [
    {
        "story_title": "قصة أصحاب الكهف",
        "surah_number": 18,
        "start_ayah": 9,
        "end_ayah": 26,
        "search_query": "قصة أصحاب الكهف ملخصة فيديو قصير",
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
# 3. Helpers
# ============================================================

def cleanup_temp_files(base_name: str) -> None:
    """
    حذف جميع الملفات المؤقتة المرتبطة باسم التحميل.
    يمنع استخدام ملفات قديمة بالخطأ.
    """

    patterns = [
        f"{base_name}.*",
    ]

    for pattern in patterns:
        for file_path in glob.glob(pattern):
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
                    print(f"🧹 تم حذف الملف المؤقت: {file_path}")
            except Exception as e:
                print(
                    f"⚠️ تعذر حذف الملف المؤقت {file_path}: {e}"
                )


def find_downloaded_video(base_name: str) -> Optional[str]:
    """
    البحث عن الفيديو النهائي فقط.
    يستبعد الملفات المؤقتة الخاصة بـ yt-dlp.
    """

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

    files = glob.glob(f"{base_name}.*")

    valid_files = []

    for file_path in files:

        if not os.path.isfile(file_path):
            continue

        extension = os.path.splitext(file_path)[1].lower()

        if extension in ignored_extensions:
            continue

        if extension not in allowed_extensions:
            continue

        if os.path.getsize(file_path) <= 0:
            continue

        valid_files.append(file_path)

    if not valid_files:
        return None

    # نختار أكبر ملف فيديو عادةً يكون الملف النهائي
    valid_files.sort(
        key=lambda path: os.path.getsize(path),
        reverse=True,
    )

    return valid_files[0]


# ============================================================
# 4. البحث وتحميل فيديو YouTube
# ============================================================

def search_and_download_youtube(
    query: str,
    output_filename: str,
) -> Optional[str]:

    print()
    print(f"🔍 البحث في يوتيوب عن:")
    print(f"   {query}")

    base_name = os.path.splitext(output_filename)[0]

    # تنظيف أي ملفات قديمة قبل بدء التحميل
    cleanup_temp_files(base_name)

    output_template = f"{base_name}.%(ext)s"

    ydl_opts = {
        # نفضل MP4 حتى يكون مناسبًا للرفع والتشغيل
        "format": (
            "bestvideo[ext=mp4][height<=1080]+"
            "bestaudio[ext=m4a]/"
            "best[ext=mp4][height<=1080]/"
            "best"
        ),

        "merge_output_format": "mp4",

        # البحث عن أول نتيجة
        "default_search": "ytsearch1:",

        "outtmpl": output_template,

        "quiet": True,

        "noplaylist": True,

        # لا نعطل التحقق من SSL
        "nocheckcertificate": False,

        "geo_bypass": True,

        "http_headers": {
            "Accept-Language": "ar,en;q=0.8",
        },
    }

    # استخدام cookies.txt فقط إذا كان موجودًا
    cookies_file = "cookies.txt"

    if os.path.exists(cookies_file):
        ydl_opts["cookiefile"] = cookies_file

    try:

        with YoutubeDL(ydl_opts) as ydl:

            info = ydl.extract_info(
                query,
                download=True,
            )

            if not info:
                print("❌ yt-dlp لم يرجع أي معلومات.")
                return None

            # إذا كانت نتيجة بحث
            if "entries" in info:

                entries = info.get("entries") or []

                if not entries:
                    print("❌ لم يتم العثور على أي فيديو.")
                    return None

                video_info = entries[0]

            else:
                video_info = info

            title = video_info.get(
                "title",
                "عنوان غير معروف",
            )

            webpage_url = video_info.get(
                "webpage_url",
                "",
            )

            duration = video_info.get(
                "duration",
                0,
            )

            print(f"🎬 الفيديو المختار: {title}")

            if webpage_url:
                print(f"🔗 المصدر: {webpage_url}")

            if duration:
                print(f"⏱️ المدة: {duration} ثانية")

            # التأكد من وجود الفيديو النهائي
            actual_file = find_downloaded_video(
                base_name
            )

            if not actual_file:

                print(
                    "❌ تم التحميل ولكن لم يتم العثور "
                    "على ملف فيديو نهائي."
                )

                return None

            print(
                f"✅ تم تحميل الفيديو بنجاح:\n"
                f"   {actual_file}"
            )

            file_size_mb = (
                os.path.getsize(actual_file)
                / (1024 * 1024)
            )

            print(
                f"📦 حجم الملف: "
                f"{file_size_mb:.2f} MB"
            )

            return actual_file

    except Exception as e:

        print(
            f"❌ حدث خطأ أثناء تحميل الفيديو:"
            f"\n{e}"
        )

        traceback.print_exc()

        return None


# ============================================================
# 5. رفع الفيديو إلى Telegram
# ============================================================

async def upload_to_telegram(
    bot: Bot,
    file_path: str,
    caption: str,
) -> Optional[str]:

    print()
    print("📤 جاري رفع الفيديو إلى Telegram...")

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
                "❌ Telegram لم يرجع معلومات الفيديو."
            )

            return None

        file_id = message.video.file_id

        file_unique_id = (
            message.video.file_unique_id
        )

        print(
            "🎉 تم الرفع بنجاح!"
        )

        print(
            f"🆔 Telegram file_id: {file_id}"
        )

        print(
            f"🔐 Telegram file_unique_id: "
            f"{file_unique_id}"
        )

        return file_id

    except Exception as e:

        print(
            f"❌ فشل رفع الفيديو إلى Telegram:"
            f"\n{e}"
        )

        traceback.print_exc()

        return None


# ============================================================
# 6. جلب السورة
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
                f"❌ لم يتم العثور على السورة "
                f"رقم {surah_number}"
            )

            return None

        return response.data["id"]

    except Exception as e:

        print(
            f"❌ خطأ أثناء جلب السورة "
            f"{surah_number}: {e}"
        )

        traceback.print_exc()

        return None


# ============================================================
# 7. جلب الآيات
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
            f"❌ خطأ أثناء جلب الآيات: {e}"
        )

        traceback.print_exc()

        return []


# ============================================================
# 8. ربط القصة بالآيات
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
        f"🔗 ربط قصة '{story_title}' "
        f"بالآيات {start_ayah} - {end_ayah}"
    )

    # --------------------------------------------------------
    # جلب السورة
    # --------------------------------------------------------

    surah_id = get_surah_id(
        surah_number
    )

    if not surah_id:
        return False

    # --------------------------------------------------------
    # جلب الآيات
    # --------------------------------------------------------

    ayahs = get_ayahs(
        surah_id,
        start_ayah,
        end_ayah,
    )

    if not ayahs:

        print(
            f"⚠️ لم يتم العثور على آيات "
            f"في النطاق {start_ayah}-{end_ayah}"
        )

        return False

    print(
        f"📌 تم العثور على {len(ayahs)} آية."
    )

    # --------------------------------------------------------
    # تحديث/إضافة كل آية
    #
    # ملاحظة:
    # ayahs_stories لا يحتوي على UNIQUE(ayah_id)
    # لذلك لا نستطيع استخدام upsert على ayah_id.
    #
    # بدلًا من ذلك:
    # 1. نبحث هل هناك سجل موجود.
    # 2. إذا موجود نعمل UPDATE.
    # 3. إذا غير موجود نعمل INSERT.
    # --------------------------------------------------------

    success_count = 0

    for ayah in ayahs:

        ayah_id = ayah["id"]

        number_in_surah = ayah[
            "number_in_surah"
        ]

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

            records = existing.data or []

            if records:

                story_id = records[0]["id"]

                (
                    supabase
                    .from_("ayahs_stories")
                    .update(
                        {
                            "title": story_title,
                            "content": (
                                f"فيديو {story_title}"
                            ),
                            "source": "YouTube",
                            "telegram_file_id": (
                                telegram_file_id
                            ),
                        }
                    )
                    .eq(
                        "id",
                        story_id,
                    )
                    .execute()
                )

                print(
                    f"🔄 تم تحديث الآية "
                    f"{number_in_surah}"
                )

            else:

                (
                    supabase
                    .from_("ayahs_stories")
                    .insert(
                        {
                            "ayah_id": ayah_id,
                            "title": story_title,
                            "content": (
                                f"فيديو {story_title}"
                            ),
                            "source": "YouTube",
                            "telegram_file_id": (
                                telegram_file_id
                            ),
                        }
                    )
                    .execute()
                )

                print(
                    f"➕ تم إضافة الآية "
                    f"{number_in_surah}"
                )

            success_count += 1

        except Exception as e:

            print(
                f"❌ فشل ربط الآية "
                f"{number_in_surah}: {e}"
            )

            traceback.print_exc()

    print()
    print(
        f"✅ تم ربط {success_count} "
        f"من أصل {len(ayahs)} آية."
    )

    return success_count == len(ayahs)


# ============================================================
# 9. التحقق هل القصة موجودة بالفعل
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
                "id,telegram_file_id"
            )
            .in_(
                "ayah_id",
                ayah_ids,
            )
            .execute()
        )

        records = response.data or []

        # إذا كانت كل الآيات لديها نفس الفيديو
        if len(records) == len(ayahs):

            file_ids = {
                record.get(
                    "telegram_file_id"
                )
                for record in records
            }

            file_ids.discard(None)

            if len(file_ids) == 1:

                print(
                    "⏭️ القصة موجودة بالفعل "
                    "بشكل كامل في Supabase."
                )

                return True

        return False

    except Exception as e:

        print(
            f"⚠️ تعذر التحقق من وجود القصة: {e}"
        )

        return False


# ============================================================
# 10. معالجة قصة واحدة
# ============================================================

async def process_story(
    bot: Bot,
    story: dict,
):

    story_title = story["story_title"]

    surah_number = story["surah_number"]

    start_ayah = story["start_ayah"]

    end_ayah = story["end_ayah"]

    print()
    print("=" * 60)
    print(
        f"🚀 بدء معالجة: {story_title}"
    )
    print("=" * 60)

    # --------------------------------------------------------
    # منع التكرار
    # --------------------------------------------------------

    if story_already_exists(
        surah_number,
        start_ayah,
        end_ayah,
    ):

        print(
            f"⏭️ تم تخطي '{story_title}' "
            f"لأنها موجودة بالفعل."
        )

        return

    # --------------------------------------------------------
    # اسم ملف فريد لكل قصة
    # --------------------------------------------------------

    base_name = (
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
        # تحميل الفيديو
        # ----------------------------------------------------

        downloaded_file = (
            search_and_download_youtube(
                story["search_query"],
                output_filename,
            )
        )

        if not downloaded_file:

            print(
                f"❌ فشل تحميل فيديو "
                f"'{story_title}'"
            )

            return

        if not os.path.exists(
            downloaded_file
        ):

            print(
                "❌ الملف غير موجود بعد التحميل."
            )

            return

        # ----------------------------------------------------
        # رفع Telegram
        # ----------------------------------------------------

        file_id = await upload_to_telegram(
            bot,
            downloaded_file,
            f"📖 {story_title}",
        )

        if not file_id:

            print(
                "❌ فشل رفع الفيديو إلى Telegram."
            )

            return

        # ----------------------------------------------------
        # ربط الفيديو بالآيات
        # ----------------------------------------------------

        success = link_story_to_supabase(
            surah_number=surah_number,
            start_ayah=start_ayah,
            end_ayah=end_ayah,
            story_title=story_title,
            telegram_file_id=file_id,
        )

        if success:

            print()
            print(
                f"🎉 اكتملت معالجة "
                f"'{story_title}' بنجاح!"
            )

        else:

            print()
            print(
                f"⚠️ تم رفع الفيديو إلى Telegram "
                f"لكن حدثت مشكلة في ربط الآيات."
            )

    except Exception as e:

        print(
            f"❌ خطأ غير متوقع أثناء معالجة "
            f"'{story_title}':\n{e}"
        )

        traceback.print_exc()

    finally:

        # ----------------------------------------------------
        # تنظيف الملفات المؤقتة دائمًا
        # ----------------------------------------------------

        cleanup_temp_files(
            base_name
        )


# ============================================================
# 11. Main
# ============================================================

async def main():

    print()
    print("=" * 60)
    print("📖 Quran Stories Processor")
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
    print("🎉 تم إنهاء جميع العمليات!")
    print("=" * 60)


# ============================================================
# 12. Entry Point
# ============================================================

if __name__ == "__main__":
    asyncio.run(main())
