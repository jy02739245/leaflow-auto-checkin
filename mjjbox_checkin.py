#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MJJBOX 自动签到脚本

环境变量支持：
  # 多账号（推荐）
  MJJBOX_ACCOUNTS = 邮箱1:密码1,邮箱2:密码2

  # 单账号
  MJJBOX_EMAIL
  MJJBOX_PASSWORD

  # Telegram（可选）
  TELEGRAM_BOT_TOKEN
  TELEGRAM_CHAT_ID

  # 站点地址（可选，默认 https://mjjbox.com）
  MJJBOX_BASE_URL

  # 是否无头模式（默认在 GitHub Actions 下自动无头）
  HEADLESS = "1" / "0"
"""

import os
import time
import logging
from datetime import datetime

import requests

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class MJJBoxAutoCheckin:
    def __init__(self, username: str, password: str):
        if not username or not password:
            raise ValueError("用户名/邮箱 和 密码 不能为空")

        self.username = username
        self.password = password

        self.base_url = os.getenv("MJJBOX_BASE_URL", "https://mjjbox.com").rstrip("/")
        self.telegram_bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID", "")

        self.driver = None
        self.setup_driver()

    # ========== 浏览器相关 ==========

    def setup_driver(self) -> None:
        """配置 Chrome / Chromium driver"""
        chrome_options = Options()

        # GitHub Actions 或 HEADLESS=1 下启用无头
        if os.getenv("GITHUB_ACTIONS") or os.getenv("HEADLESS", "1") == "1":
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-gpu")
            chrome_options.add_argument("--window-size=1920,1080")

        # 一些常规参数 & 反自动化
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option("useAutomationExtension", False)

        self.driver = webdriver.Chrome(options=chrome_options)

        # 去掉 webdriver 标记
        try:
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
        except Exception:
            pass

    def wait_clickable(self, by, value, timeout: int = 10):
        return WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )

    def wait_present(self, by, value, timeout: int = 10):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, value))
        )

    # ========== 登录相关 ==========

    def login(self) -> bool:
        """登录 MJJBOX"""
        login_url = f"{self.base_url}/login"
        logger.info(f"开始登录 {login_url}")

        self.driver.get(login_url)
        time.sleep(5)

        # 用户名/邮箱输入框（你提供的 id）
        try:
            username_input = self.wait_clickable(By.ID, "login-account-name", 10)
        except Exception:
            raise RuntimeError("找不到用户名/邮箱输入框 (id=login-account-name)")

        username_input.clear()
        username_input.send_keys(self.username)
        logger.info("用户名/邮箱输入完成")

        time.sleep(1)

        # 密码输入框（你提供的 id）
        try:
            password_input = self.wait_clickable(By.ID, "login-account-password", 10)
        except Exception:
            raise RuntimeError("找不到密码输入框 (id=login-account-password)")

        password_input.clear()
        password_input.send_keys(self.password)
        logger.info("密码输入完成")

        time.sleep(1)

        # 登录按钮，你之前改过的选择器
        login_button_selectors = [
            "#login-button",
            "button.btn-primary",
            "//button[contains(text(), '登录')]",
            "//button[contains(text(), 'Log in')]",
        ]

        login_btn = None
        for selector in login_button_selectors:
            try:
                if selector.startswith("//"):
                    login_btn = WebDriverWait(self.driver, 5).until(
                        EC.element_to_be_clickable((By.XPATH, selector))
                    )
                else:
                    login_btn = self.wait_clickable(By.CSS_SELECTOR, selector, 5)
                break
            except Exception:
                continue

        if not login_btn:
            raise RuntimeError("找不到登录按钮，请检查页面结构")

        login_btn.click()
        logger.info("已点击登录按钮，等待登录完成...")

        # 简单判断：URL 不再包含 /login 视为登录成功
        try:
            WebDriverWait(self.driver, 20).until(
                lambda d: "/login" not in d.current_url
            )
        except Exception:
            logger.warning(f"登录后 URL 仍为 {self.driver.current_url}，可能登录失败")
            return False

        logger.info(f"登录完成，当前 URL: {self.driver.current_url}")
        return True

    # ========== CSRF & 签到请求 ==========

    def get_csrf_token(self) -> str:
        """
        从 <meta name="csrf-token" content="..."> 中获取 CSRF Token
        Discourse 默认就是这么放的
        """
        try:
            meta = self.driver.find_element(By.CSS_SELECTOR, "meta[name='csrf-token']")
            token = meta.get_attribute("content") or ""
            token = token.strip()
            if token:
                logger.info("成功获取 CSRF Token")
                return token
        except Exception as e:
            logger.warning(f"获取 CSRF Token 失败: {e}")

        return ""

    def perform_checkin_request(self) -> tuple[str, str]:
        """
        模拟油猴脚本的 _performCheckinRequest：
        向 /checkin 发送 POST 请求，返回 (结果类型, 提示文本)

        结果类型：
          - "success"  : 签到成功
          - "duplicate": 今天已经签到过了
          - "auth"     : 权限 / 登录问题
          - "error"    : 其他错误
        """
        csrf_token = self.get_csrf_token()
        if not csrf_token:
            raise RuntimeError("无法获取 CSRF Token，请确认已经成功登录")

        # 用 Selenium 当前 session 的 cookie 构造一个 requests.Session
        session = requests.Session()
        for c in self.driver.get_cookies():
            try:
                session.cookies.set(c["name"], c["value"])
            except Exception:
                continue

        headers = {
            "Accept": "application/json",
            "X-CSRF-Token": csrf_token,
            "X-Requested-With": "XMLHttpRequest",
        }

        url = f"{self.base_url}/checkin"
        logger.info(f"向 {url} 发送签到请求")

        try:
            resp = session.post(url, headers=headers, timeout=15)
        except Exception as e:
            logger.error(f"签到请求发送失败: {e}")
            return "error", f"签到请求发送失败: {e}"

        status = resp.status_code
        text = resp.text or ""
        text_lower = text.lower()

        logger.info(f"签到响应 HTTP 状态码：{status}")

        # 参照你油猴脚本的逻辑：422 代表校验失败 / 已签到等
        if status == 422:
            if (
                "already checked in" in text_lower
                or "已经签到过" in text_lower
                or "duplicate" in text_lower
            ):
                return "duplicate", "您今天已经签到过了"
            else:
                return "error", "安全验证失败，请刷新页面或重新登录 (422)"

        if status == 403:
            return "auth", "权限不足或未登录，请重新登录 (403)"

        # 200 尝试解析 JSON
        if status == 200:
            try:
                data = resp.json()
            except Exception:
                msg = text.strip() or "签到完成（非 JSON 响应）"
                return "success", msg

            success = bool(data.get("success", False))
            message = (
                data.get("message")
                or data.get("msg")
                or data.get("detail")
                or "签到完成"
            )

            if success:
                return "success", message
            else:
                return "error", f"签到失败：{message}"

        # 其他 HTTP 状态码
        return (
            "error",
            f"签到失败，HTTP 状态码：{status}，响应内容前 200 字：{text[:200]}",
        )

    # ========== 外部调用的主流程 ==========

    def checkin(self) -> str:
        """整体签到流程：登录 + 打开页面拿 CSRF + 调用 /checkin 接口"""
        logger.info(f"开始为账号 {self.username} 签到")

        if not self.login():
            raise RuntimeError("登录失败，无法进行签到")

        # 为了拿到 meta[name='csrf-token']，打开首页或任意页面
        try:
            self.driver.get(f"{self.base_url}/")
            time.sleep(5)
        except Exception as e:
            logger.warning(f"打开首页失败: {e}")

        result_type, message = self.perform_checkin_request()

        if result_type == "success":
            logger.info(f"签到成功：{message}")
            return f"签到成功：{message}"
        elif result_type == "duplicate":
            logger.info(message)
            return message
        elif result_type == "auth":
            logger.error(message)
            raise RuntimeError(message)
        else:
            logger.error(message)
            raise RuntimeError(message)

    # ========== Telegram 通知 ==========

    def send_telegram(self, message: str) -> None:
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return

        try:
            url = f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage"
            data = {
                "chat_id": self.telegram_chat_id,
                "text": message,
                "parse_mode": "HTML",
            }
            resp = requests.post(url, data=data, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"Telegram 推送失败：{resp.text}")
        except Exception as e:
            logger.warning(f"Telegram 推送异常: {e}")

    # ========== 资源回收 ==========

    def close(self):
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass


# ========== 多账号解析 ==========

def parse_accounts_from_env():
    """
    支持两种方式：
    1. 多账号：
       MJJBOX_ACCOUNTS = 邮箱1:密码1,邮箱2:密码2

    2. 单账号：
       MJJBOX_EMAIL / MJJBOX_PASSWORD
    """
    accounts = []

    accounts_var = os.getenv("MJJBOX_ACCOUNTS", "").strip()
    if accounts_var:
        for pair in accounts_var.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            user, pwd = pair.split(":", 1)
            user = user.strip()
            pwd = pwd.strip()
            if user and pwd:
                accounts.append((user, pwd))

    if not accounts:
        user = os.getenv("MJJBOX_EMAIL", "").strip()
        pwd = os.getenv("MJJBOX_PASSWORD", "").strip()
        if user and pwd:
            accounts.append((user, pwd))

    return accounts


# ========== 主入口 ==========

def main():
    accounts = parse_accounts_from_env()
    if not accounts:
        logger.error(
            "未找到账号配置，请设置环境变量：\n"
            "  多账号：MJJBOX_ACCOUNTS = 邮箱1:密码1,邮箱2:密码2\n"
            "  或 单账号：MJJBOX_EMAIL / MJJBOX_PASSWORD"
        )
        return

    overall_messages = []
    for idx, (user, pwd) in enumerate(accounts, start=1):
        logger.info("=" * 60)
        logger.info(f"开始处理第 {idx} 个账号：{user}")

        checker = MJJBoxAutoCheckin(user, pwd)
        try:
            result = checker.checkin()
            msg = f"账号 {user} 签到成功：{result}"
            logger.info(msg)
        except Exception as e:
            msg = f"账号 {user} 签到失败：{e}"
            logger.error(msg)
        finally:
            checker.close()

        overall_messages.append(msg)
        # 多账号间稍微停顿一下，避免太频繁
        time.sleep(5)

    final_text = "MJJBOX 每日签到结果：\n" + "\n".join(overall_messages)
    logger.info(final_text)

    # 汇总结果推送 Telegram
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if bot_token and chat_id:
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            requests.post(
                url,
                data={"chat_id": chat_id, "text": final_text},
                timeout=10,
            )
        except Exception as e:
            logger.warning(f"汇总结果 Telegram 推送失败: {e}")


if __name__ == "__main__":
    main()
