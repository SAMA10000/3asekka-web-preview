import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from gradio_client import Client

OUT = Path("generated/namaa-safety")
OUT.mkdir(parents=True, exist_ok=True)

GENERAL = """أهلاً بيك في عالسكة. قبل ما تكمل، اسمع قواعد الأمان دي كويس. الاحترام إلزامي، وممنوع الشتيمة أو التهديد أو التحرش أو التمييز أو أي إساءة للطرف التاني. الاتفاق على النقلة والسعر الأساسي والتواصل المرتبط بيها يفضل داخل عالسكة، وممنوع تبادل أرقام أو روابط بهدف تنفيذ النقلة أو الاتفاق خارج التطبيق. ممنوع استخدام عالسكة لنقل بضائع غير قانونية أو مسروقة أو محظورة، أو إخفاء طبيعة حمولة خطرة أو مقيدة. ممنوع مشاركة كلمات المرور أو بيانات الدفع السرية أو صور المستندات الشخصية داخل الشات. التزم بالسلامة، وما تطلبش ولا تنفذ حمولة أو قيادة تعرض أي شخص أو العربية أو الطريق للخطر. كعميل، اكتب نوع الحمولة ووزنها وحجمها وعناوين الاستلام والتسليم بدقة، وما تطلبش من السائق حمولة زائدة أو مخالفة للطريق أو نقلة لبضاعة ما تملكش حق إرسالها. وكسائق، استخدم العربية المعتمدة على حسابك بمستندات سارية، والتزم بالحمولة الآمنة وحالة الرحلة الحقيقية، وارفض الحمولة لو اختلفت بشكل جوهري عن الوصف أو بدت غير قانونية أو غير آمنة. إدارة عالسكة ممكن تراجع المحادثات وسجل المكالمات الداخلية وحالتها ومدتها عند الحاجة للأمان وحل النزاعات، لكن صوت المكالمة نفسه مش بيتسجل في النظام الحالي. أي مخالفة جسيمة أو متكررة ممكن تؤدي لتحذير الحساب أو تقييده أو إيقافه بعد مراجعة الإدارة."""

COMMUNICATION = """خلي اتفاقك جوه عالسكة. لأمان حقك وحق الطرف التاني، خلي السعر والاتفاق والتواصل المرتبط بالنقلة داخل عالسكة. ممنوع تبادل أرقام أو روابط بهدف تنفيذ النقلة أو الاتفاق خارج التطبيق. لو اتفقتوا أو دفعتوا خارج عالسكة، ممكن ما نقدرش نتحقق من تفاصيل الاتفاق أو نساعدكم بنفس الدرجة لو حصل نزاع. محادثات عالسكة وسجل المكالمات الداخلية ممكن تراجعها الإدارة لأغراض الأمان وحل النزاعات. المكالمات الصوتية نفسها لا يتم تسجيلها."""


def chunks(text: str, limit: int = 250):
    text = re.sub(r"\s+", " ", text.strip())
    sentences = re.split(r"(?<=[.!؟،])\s+", text)
    result, current = [], ""
    for sentence in sentences:
        if len(sentence) > limit:
            for word in sentence.split():
                candidate = (current + " " + word).strip()
                if len(candidate) <= limit:
                    current = candidate
                else:
                    if current:
                        result.append(current)
                    current = word
            continue
        candidate = (current + " " + sentence).strip()
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                result.append(current)
            current = sentence
    if current:
        result.append(current)
    return result


def result_path(result):
    if isinstance(result, str):
        return Path(result)
    if isinstance(result, dict):
        for key in ("path", "name"):
            value = result.get(key)
            if isinstance(value, str) and value:
                return Path(value)
    if isinstance(result, (list, tuple)):
        for item in result:
            try:
                return result_path(item)
            except Exception:
                pass
    raise RuntimeError(f"Cannot resolve generated audio path: {result!r}")


def synthesize(client: Client, text: str):
    attempts = [
        lambda: client.predict(text, "ar", None, 0.5, 0.8, 0, 0.5, api_name="/generate_tts_audio"),
        lambda: client.predict(text, None, 0.5, 0.8, 0, 0.5, api_name="/generate_tts_audio"),
    ]
    errors = []
    for call in attempts:
        try:
            return call()
        except Exception as exc:
            errors.append(repr(exc))
            print("NAMAA_CALL_FAILED", repr(exc), flush=True)
            time.sleep(3)
    raise RuntimeError("NAMAA generation failed: " + " | ".join(errors))


def render(client: Client, label: str, text: str):
    parts = []
    for index, chunk in enumerate(chunks(text), 1):
        print(f"Generating {label} part {index}: {chunk}", flush=True)
        generated = result_path(synthesize(client, chunk))
        suffix = generated.suffix or ".wav"
        destination = OUT / f"{label}_{index:02d}{suffix}"
        shutil.copyfile(generated, destination)
        parts.append(destination)

    concat = OUT / f"{label}_concat.txt"
    concat.write_text("".join(f"file '{p.resolve()}'\n" for p in parts), encoding="utf-8")

    wav = OUT / f"{label}.wav"
    mp3 = OUT / f"{label}.mp3"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-ar", "24000", "-ac", "1", str(wav)], check=True)
    subprocess.run(["ffmpeg", "-y", "-i", str(wav), "-codec:a", "libmp3lame", "-b:a", "96k", str(mp3)], check=True)

    if wav.stat().st_size < 1000 or mp3.stat().st_size < 1000:
        raise RuntimeError(f"Generated audio is unexpectedly small for {label}")

    return wav, mp3


def main():
    client = Client(os.environ.get("HF_SPACE", "omarelshehy/NAMAA-Egyptian-Voice"))
    try:
        print(client.view_api(return_format="dict"), flush=True)
    except Exception as exc:
        print("VIEW_API_WARNING", repr(exc), flush=True)

    general = render(client, "safety_general", GENERAL)
    communication = render(client, "communication_warning", COMMUNICATION)
    print("DONE", general, communication, flush=True)


if __name__ == "__main__":
    main()
