"""跨线程信号定义模块。

定义全部跨线程 Qt 信号，分两个 ``QObject`` 子类承载：
- ``WorkerSignals``：工作线程 → UI 方向信号（由桥接器 emit，UI 槽接收）
- ``ControlSignals``：UI → 工作线程方向信号（由 UI emit，桥接器槽接收）

严格遵循设计文档 2.3 节（线程模型）与 v0.0.6 计划文档任务 2。

信号参数类型说明：
    - ``Signal(list)`` 的 list 元素类型在文档中明确，Qt 运行时不强制校验元素类型，
      由桥接器保证传入正确类型。
    - ``progress_updated`` 的 list 元素是 ``ProgressUpdate``（v0.0.5）
    - ``parse_completed`` 的 list 元素是 ``ParsedURL``（v0.0.3）
    - ``home_fetch_completed`` 的 list 元素是 ``PostItem``（v0.0.4）
    - ``start_download`` 的 list 元素是 ``int``（task_item_id）
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class WorkerSignals(QObject):
    """工作线程 → UI 方向信号。

    由 ``DownloadBridge`` / ``CrawlerBridge`` 在工作线程中 ``emit``，
    UI 线程的槽函数接收（Qt 自动跨线程投递，使用 ``Qt.QueuedConnection``）。
    """

    # === 下载相关 ===

    # list[ProgressUpdate]，批量进度更新（每 500ms 由 ProgressReporter 触发）
    progress_updated = Signal(list)

    # task_item_id，某任务项下载完成
    item_completed = Signal(int)

    # task_item_id, fail_reason，某任务项下载失败
    item_failed = Signal(int, str)

    # message，Cookie 全部失效提示文案
    cookie_invalid = Signal(str)

    # task_id，某任务下所有子项完成
    task_completed = Signal(int)

    # v0.1.6：task_id，一批任务项已加入下载队列（用户反馈 #6）
    # DownloadBridge._do_start_download 中 scheduler.add_task_items 成功后 emit，
    # 供 FetchPage 在入队成功后清理输入框/结果列表/过滤栏/全选状态
    download_started = Signal(int)

    # === 解析相关 ===

    # current（当前已解析数）, total（总链接数）
    parse_progress = Signal(int, int)

    # list[ParsedURL]，链接解析完成的结果列表
    parse_completed = Signal(list)

    # reason，链接解析失败原因
    parse_failed = Signal(str)

    # === Cookie 测试 ===

    # cookie_id, is_valid, message
    cookie_test_result = Signal(int, bool, str)

    # === 主页抓取 ===

    # current（已抓取数）, total（预计总数，未知时为 0）
    home_fetch_progress = Signal(int, int)

    # list[PostItem]，主页抓取完成的作品列表
    home_fetch_completed = Signal(list)

    # reason，主页抓取失败原因
    home_fetch_failed = Signal(str)


class ControlSignals(QObject):
    """UI → 工作线程方向信号。

    由 UI 线程 ``emit``，桥接器的槽函数在工作线程接收并执行。
    """

    # === 下载控制 ===

    # list[int]（task_item_id 列表），开始下载
    start_download = Signal(list)

    # task_item_id，暂停某个任务项
    pause_download = Signal(int)

    # task_item_id，恢复某个任务项
    resume_download = Signal(int)

    # 无参数，全部暂停
    pause_all = Signal()

    # 无参数，全部恢复
    resume_all = Signal()

    # === 解析控制 ===

    # text（用户粘贴的链接文本）
    start_parse = Signal(str)

    # 无参数，取消正在进行的解析
    cancel_parse = Signal()

    # === 主页抓取控制 ===

    # sec_user_id, filters（dict 形式，含 type_filter/max_count/start_date/end_date）
    start_home_fetch = Signal(str, dict)

    # 无参数，取消正在进行的主页抓取
    cancel_home_fetch = Signal()

    # === Cookie 测试控制 ===

    # cookie_id，测试某条 Cookie
    test_cookie = Signal(int)

    # 无参数，测试所有 Cookie
    test_all_cookies = Signal()
