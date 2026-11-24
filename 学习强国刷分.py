# -*- coding: utf-8 -*-
"""
============================================================
学习强国 App 自动刷分（安卓模拟器版）
============================================================

【功能】
    自动完成以下积分项：
        1. 选读文章（找没看过的，每篇读 1 分钟以上，共 6 篇 → 阅读 12 分）
        2. 视听学习（进「百灵」，自动连播，每个视频播满 1 分钟就上滑换下一个，
                   总播放 6 分半 → 视听 12 分）
    答题类项目不处理。

【重要规则】
    文章的「按篇」分和「按时长」分是分开的：
      - 每篇文章，当天第一次打开才算一次有效阅读（按篇分）。重复打开不再计按篇分。
      - 但时长分照样累计，所以只要每篇读满 1 分钟就行。
    脚本把已读文章的标题记在 已读记录.txt（按日期分节、跨天去重），
    确保只挑没看过的文章。

    视听走「百灵」，百灵每天刷新、不会和前一天重复，所以不用记名字：
    进去后随便点一个视频，会竖屏自动连播；每播满 1 分钟上滑换下一个，
    总播 6 分半即可拿满视听 12 分。

【运行环境准备（换电脑必读）】
    1. 安装 Python 3.10+（建议 3.12/3.13，太新的 3.14 部分库可能编译失败）
    2. 安装依赖（命令行执行）：
           pip install -U uiautomator2
       这会连带安装 adbutils / requests 等。
       首次连接设备时，uiautomator2 会自动往模拟器里装一个
       uiautomator-server 组件（模拟器需能联网或已授权安装）。

    3. 安装 MuMu 模拟器 12，并在里面装好「学习强国」App、手动登录一次。

    4. 找到 MuMu 的 adb 程序。默认安装位置：
           D:\\Program Files\\Netease\\MuMu\\nx_main\\adb.exe
       如果你的安装位置不同，请修改下面 ADB_PATH。
       （MuMu 安装目录下通常有两处 adb：nx_main\\adb.exe 与
         nx_device\\<版本>\\shell\\adb.exe，用 nx_main 下的即可）

    5. MuMu 12 的 adb 默认端口是 7555。若你改过，请修改 ADB_ADDR。
       端口可这样确认（Windows 命令行）：
           netstat -ano | findstr 7555
       只要看到 127.0.0.1:7555 LISTENING 即可。

    6. 端口与地址确认连上：
           adb connect 127.0.0.1:7555
           adb devices
       应显示  127.0.0.1:7555   device

【使用】
    学习强国已在模拟器里登录过一次即可，之后直接运行本脚本：
    若模拟器没开，脚本会自动启动它、等开机，再连接并切到 App，最后执行阅读与视听。
    运行记录写在同目录 运行记录.txt。

【停止】
    直接关掉黑窗口，或按 Ctrl+C。
============================================================
"""

import os
import re
import sys
import time
import json
import subprocess

import uiautomator2 as u2

# ------------------------------------------------------------------
# 配置区：换电脑主要改这里
# ------------------------------------------------------------------

# MuMu adb 程序路径（注意 Windows 下用双反斜杠或原始字符串）
ADB_PATH = r"E:\Program Files\YXArkNights-12.0\shell\adb.exe"

# MuMu 实例管理器（用于自动启动模拟器；在 adb 同目录）
MUMU_MANAGER = r"E:\Program Files\YXArkNights-12.0\shell\MuMuManager.exe"

# MuMu 实例编号（默认第 0 个；多开时按需改）
MUMU_INDEX = 0

# MuMu adb 端口地址
ADB_ADDR = "127.0.0.1:7555"

# 学习强国包名
PKG = "cn.xuexi.android"

# 每篇文章停留的秒数：必须 ≥ 60 秒（阅读累计时长要满 1 分钟才拿时长分）
READ_DWELL = 62

# 文章篇数：每篇 1 分钟以上，看 6 篇即可拿满阅读 12 分
ARTICLE_BATCH = 6

# 视听：每个视频播放的秒数，播满 1 分钟以上就上滑换下一个（避免长视频卡住）
VIDEO_DWELL = 62

# 视听总播放秒数：6.5 分钟（拿满视听 12 分且留容错）
WATCH_TOTAL_SEC = 400

# ------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(HERE, "运行记录.txt")
SEEN_FILE = os.path.join(HERE, "已读记录.txt")


def log(msg):
    line = "[%s] %s" % (time.strftime("%H:%M:%S"), msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


# ------------------------------------------------------------------
# adb / 设备连接
# ------------------------------------------------------------------

def adb_device_online():
    """判断目标 adb 地址当前是否在线。"""
    try:
        out = subprocess.run([ADB_PATH, "devices"],
                             capture_output=True, timeout=15).stdout.decode("utf-8", "ignore")
        for line in out.splitlines():
            if line.startswith(ADB_ADDR) and "device" in line and "offline" not in line:
                return True
    except Exception:
        pass
    return False


def start_emulator_and_wait(timeout=180):
    """启动 MuMu 实例并等它开机完成。"""
    if not os.path.exists(MUMU_MANAGER):
        log("找不到 MuMuManager，跳过自动启动")
        return False
    log("模拟器未就绪，正在启动 MuMu...")
    try:
        subprocess.run([MUMU_MANAGER, "control", "-v", str(MUMU_INDEX), "launch"],
                       capture_output=True, timeout=30)
    except Exception as e:
        log(f"启动模拟器失败：{e}")
        return False
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            out = subprocess.run([MUMU_MANAGER, "info", "-v", str(MUMU_INDEX)],
                                 capture_output=True, timeout=15).stdout.decode("utf-8", "ignore")
            if '"start_finished"' in out and '"is_android_started": true' in out:
                log(f"模拟器已开机（{int(time.time() - t0)}s）")
                time.sleep(3)
                return True
        except Exception:
            pass
        time.sleep(5)
    log("等待模拟器开机超时")
    return False


def ensure_adb_connected():
    """确保模拟器已开机且 adb 连上。"""
    if not adb_device_online():
        start_emulator_and_wait()
    for _ in range(10):
        if os.path.exists(ADB_PATH):
            try:
                subprocess.run([ADB_PATH, "connect", ADB_ADDR],
                               capture_output=True, timeout=15)
            except Exception as e:
                log(f"adb connect 失败：{e}")
        if adb_device_online():
            break
        time.sleep(3)
    return u2.connect(ADB_ADDR)


def wait_app_ready(d, timeout=40):
    """确保学习强国在前台首页。"""
    def at_home():
        cur = d.app_current()
        return cur.get("package") == PKG and "HomeActivity" in cur.get("activity", "")

    if at_home():
        return True

    # 先尝试返回，逐步退回首页
    for _ in range(10):
        if at_home():
            return True
        try:
            d.press("back")
        except Exception:
            pass
        time.sleep(1.2)

    # 还不在首页，用真实启动页拉起 App
    try:
        subprocess.run([ADB_PATH, "-s", ADB_ADDR, "shell", "am", "start",
                        "-n", f"{PKG}/com.alibaba.android.rimet.biz.SplashActivity"],
                       capture_output=True, timeout=15)
    except Exception:
        pass
    for _ in range(timeout):
        if at_home():
            return True
        time.sleep(1)
    return at_home()


def go_home(d, tries=6):
    """按返回直到回到首页。"""
    for _ in range(tries):
        cur = d.app_current()
        if cur.get("package") == PKG and "HomeActivity" in cur.get("activity", ""):
            return True
        d.press("back")
        time.sleep(1.2)
    return False


def is_jifen_page(d):
    cur = d.app_current()
    return "CommonWebViewActivity" in cur.get("activity", "")


# ------------------------------------------------------------------
# 已读记录（按日期分节）
# ------------------------------------------------------------------

def today():
    return time.strftime("%Y-%m-%d")


def load_seen():
    """读取今天的已处理标题集合。"""
    seen = set()
    if not os.path.exists(SEEN_FILE):
        return seen
    cur = None
    try:
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n")
                if line.startswith("# "):
                    cur = line[2:].strip()
                elif cur == today() and line.strip():
                    seen.add(line.strip())
    except Exception:
        pass
    return seen


def append_seen(title):
    """把标题追加到今天这节。"""
    exists = os.path.exists(SEEN_FILE)
    need_header = True
    if exists:
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                if f"# {today()}" in f.read():
                    need_header = False
        except Exception:
            pass
    with open(SEEN_FILE, "a", encoding="utf-8") as f:
        if need_header:
            f.write(f"\n# {today()}\n")
        f.write(title.strip() + "\n")


# ------------------------------------------------------------------
# 界面解析工具
# ------------------------------------------------------------------

def dump_xml(d):
    try:
        return d.dump_hierarchy()
    except Exception:
        return ""


def text_nodes(xml):
    """返回 [(text, (l,t,r,b), clickable)] 仅 TextView 有文字的。"""
    out = []
    for m in re.finditer(r"<node[^>]*class=\"android\.widget\.TextView\"[^>]*>", xml):
        tag = m.group(0)
        t = re.search(r"text=\"([^\"]*)\"", tag)
        b = re.search(r"bounds=\"\[(\d+),(\d+)\]\[(\d+),(\d+)\]\"", tag)
        c = re.search(r"clickable=\"([^\"]*)\"", tag)
        if not t or not t.group(1) or not b:
            continue
        txt = t.group(1)
        bounds = tuple(int(x) for x in b.groups())
        clk = (c.group(1) == "true") if c else False
        out.append((txt, bounds, clk))
    return out


SKIP_WORDS = (
    "推荐", "要闻", "思想", "乡村阅读", "发现", "本地", "综合", "融媒中心",
    "强国通", "百灵", "学习", "电视台", "电台", "积分", "我的", "播报",
    "全部", "第一频道", "视野", "联播频道", "看电视", "看理论", "看党史",
    "看教育", "看慕课", "学习新视界", "奋斗新时代", "重要活动", "重要会议",
    "重要讲话", "重要文章", "观点", "评论", "分享", "点赞", "听视频",
    "欢迎发表观点", "进入习近平文汇频道查看更多内容",
)

SKIP_PATTERNS = (
    r"^\d{4}-\d{2}-\d{2}$",
    r"^\d{1,2}:\d{2}$",
    r"^\d{1,2}:\d{2} / \d{1,2}:\d{2}$",
    r"^[\d,\.]+万?播放$",
    r"^[\d,\.]+万?$",
    r"^[\ue000-\uf8ff]+$",
    r"^来源：",
    r"^责任编辑",
    r"^第\d+",
)


def is_article_title(txt):
    if len(txt) < 12:
        return False
    if txt in SKIP_WORDS:
        return False
    for p in SKIP_PATTERNS:
        if re.match(p, txt):
            return False
    return True


def click_bounds(d, bounds):
    l, t, r, b = bounds
    d.click((l + r) // 2, (t + b) // 2)


# ------------------------------------------------------------------
# 积分页
# ------------------------------------------------------------------

def open_jifen_page(d):
    """打开 我的 -> 学习积分。"""
    go_home(d)
    d.click(860, 70)
    time.sleep(3)
    el = d(description="学习积分")
    if not el.exists:
        log("没找到「学习积分」入口")
        return False
    b = el.info["bounds"]
    d.click((b["left"] + b["right"]) // 2, (b["top"] + b["bottom"]) // 2)
    time.sleep(5)
    return is_jifen_page(d)


def read_scores(d):
    """从积分页读取 今日总分 与 各任务分。返回 dict。"""
    if not jifen_page_visible(d):
        open_jifen_page(d)
    xml = dump_xml(d)
    info = {"total_points": None, "today": None, "article_txt": None, "video_txt": None}
    for txt, bounds, _ in text_nodes(xml):
        if re.match(r"^\d{4,6}$", txt) and bounds[1] < 400 and bounds[0] > 250:
            try:
                info["total_points"] = int(txt)
            except Exception:
                pass
        m = re.match(r"今日已累积\s*(\d+)\s*积分", txt)
        if m:
            info["today"] = int(m.group(1))
        if txt == "我要选读文章":
            info["_article_anchor"] = bounds
        if txt == "我要视听学习":
            info["_video_anchor"] = bounds
    # 用锚点下一行的 "x分/12分" 找进度
    rows = text_nodes(xml)
    def score_after(anchor_top):
        best = None
        for txt, bounds, _ in rows:
            m = re.match(r"^(\d+)分/(\d+)分$", txt)
            if m and bounds[1] > anchor_top and (best is None or bounds[1] < best[1]):
                best = (txt, bounds[1])
        return best[0] if best else None
    if "_article_anchor" in info:
        info["article_txt"] = score_after(info["_article_anchor"][1])
    if "_video_anchor" in info:
        info["video_txt"] = score_after(info["_video_anchor"][1])
    return info


def jifen_page_visible(d):
    xml = dump_xml(d)
    return "积分中心" in xml


def goto_task(d, keyword):
    """在积分页点击某任务右侧的「去看看」。keyword: 我要选读文章 / 我要视听学习"""
    xml = dump_xml(d)
    anchor_top = None
    for txt, bounds, _ in text_nodes(xml):
        if txt == keyword:
            anchor_top = bounds[1]
            break
    if anchor_top is None:
        log(f"积分页上没找到任务：{keyword}")
        return False
    # 找该任务下方最近的「去看看」
    best = None
    for txt, bounds, clk in text_nodes(xml):
        if txt == "去看看" and bounds[1] > anchor_top:
            if best is None or bounds[1] < best[1]:
                best = bounds
    if best is None:
        # 可能"去看看"没渲染出来，直接点任务行右侧区域
        log(f"  任务 {keyword} 没找到「去看看」，尝试点右侧区域")
        d.click(760, anchor_top + 45)
    else:
        click_bounds(d, best)
    time.sleep(5)
    return True


# ------------------------------------------------------------------
# 阅读文章
# ------------------------------------------------------------------

def collect_titles_on_screen(d):
    xml = dump_xml(d)
    out = []
    for txt, bounds, clk in text_nodes(xml):
        if is_article_title(txt):
            out.append((txt, bounds))
    return out


def read_articles(d, seen):
    """在学习页读文章。返回本轮处理数量。"""
    log("开始阅读文章")
    go_home(d)
    # 确保在"学习"页
    d.click(450, 1555)
    time.sleep(2)

    done = 0
    scrolls = 0
    while done < ARTICLE_BATCH and scrolls < 12:
        titles = collect_titles_on_screen(d)
        picked = [(t, b) for t, b in titles if t not in seen]
        if not picked:
            d.swipe(450, 1300, 450, 600, 0.3)
            time.sleep(2)
            scrolls += 1
            continue
        title, bounds = picked[0]
        log(f"  阅读：{title[:30]}")
        click_bounds(d, bounds)
        time.sleep(3)
        cur = d.app_current()
        if "HomeActivity" in cur.get("activity", ""):
            log("    没打开详情，跳过")
            seen.add(title)
            append_seen(title)
            scrolls += 1
            continue
        # 停留读满 1 分钟以上（拿时长分；不滑动，避免打断计时）
        t0 = time.time()
        while time.time() - t0 < READ_DWELL:
            time.sleep(2)
        dwell = time.time() - t0
        d.press("back")
        time.sleep(2)
        seen.add(title)
        append_seen(title)
        done += 1
        log(f"    停留 {dwell:.0f}s，累计 {done} 篇")
        # 回到学习页顶部附近
        go_home(d)
        d.click(450, 1555)
        time.sleep(1.5)
    log(f"文章本轮完成 {done} 篇")
    return done


# ------------------------------------------------------------------
# 观看视频（百灵：每天刷新，自动连播）
# ------------------------------------------------------------------

# 百灵入口（底部第 2 个 tab）
BAILING_X = 225
BAILING_Y = 1545


def watch_videos(d, seen):
    """进百灵随便点一个视频，自动连播；每播满 1 分钟上滑换下一个，总播 6 分半。"""
    log("开始视听学习（百灵）")
    go_home(d)
    d.click(BAILING_X, BAILING_Y)
    time.sleep(3)

    # 找一个视频卡片点进去（卡片标题 clickable=true，位于中下部）
    if not enter_bailing_video(d):
        log("  百灵里没找到可点的视频，放弃本轮视听")
        return 0

    t_start = time.time()
    n = 0
    while time.time() - t_start < WATCH_TOTAL_SEC:
        # 当前视频播满 1 分钟（不足时会连播到下一个，也会继续累计）
        t0 = time.time()
        while time.time() - t0 < VIDEO_DWELL and time.time() - t_start < WATCH_TOTAL_SEC:
            time.sleep(2)
        n += 1
        log(f"    第 {n} 段播放结束，已播 {time.time() - t_start:.0f}s")
        if time.time() - t_start >= WATCH_TOTAL_SEC:
            break
        # 上滑换下一个视频
        d.swipe(450, 1300, 450, 500, 0.3)
        time.sleep(2)

    log(f"视听累计播放 {time.time() - t_start:.0f}s，共 {n} 段")
    go_home(d)
    return n


def enter_bailing_video(d):
    """在百灵页点一个视频卡片。返回是否成功进入播放页。"""
    for _ in range(4):
        xml = dump_xml(d)
        cands = []
        for txt, bounds, clk in text_nodes(xml):
            if not clk:
                continue
            if len(txt) < 8:
                continue
            if bounds[1] > 300 and bounds[3] < 1500:
                cands.append(bounds)
        if cands:
            click_bounds(d, cands[0])
            time.sleep(4)
            if "Window2Activity" in d.app_current().get("activity", ""):
                return True
        d.swipe(450, 1300, 450, 700, 0.3)
        time.sleep(2)
    return False


# ------------------------------------------------------------------
# 主流程
# ------------------------------------------------------------------

def main():
    log("=" * 52)
    log("学习强国 App 刷分启动")

    d = ensure_adb_connected()
    try:
        log(f"设备：{json.dumps(d.info, ensure_ascii=False)}")
    except Exception as e:
        log(f"设备信息读取失败：{e}")
        return

    if not wait_app_ready(d):
        log("学习强国没有进入首页，请确认 App 已登录并在前台")
        return

    seen = load_seen()
    log(f"今日已记录 {len(seen)} 条")

    info = read_scores(d)
    log(f"当前：总分={info.get('total_points')} 今日={info.get('today')} "
        f"文章={info.get('article_txt')}")

    art = info.get("article_txt") or ""
    m_art = re.match(r"(\d+)分/(\d+)分", art)
    art_done = m_art and int(m_art.group(1)) >= int(m_art.group(2))

    if not art_done:
        open_jifen_page(d)
        goto_task(d, "我要选读文章")
        read_articles(d, seen)
    else:
        log("文章已满，跳过")

    # 视听：百灵每天刷新，直接跑满 6 分半（拿满 12 分）
    watch_videos(d, seen)

    final = read_scores(d)
    log(f"结束：总分={final.get('total_points')} 今日={final.get('today')} "
        f"文章={final.get('article_txt')}")
    log("答题类项目请手动完成。")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log("已手动中断")
    except Exception as e:
        import traceback
        log("异常退出：\n" + traceback.format_exc())
    if sys.stdin and sys.stdin.isatty():
        try:
            input("\n按回车键退出...")
        except EOFError:
            pass
