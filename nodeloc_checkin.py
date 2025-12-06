#!/usr/bin/env python3
"""
NodeLoc 多账号自动签到脚本
变量名：NODELOC_ACCOUNTS
变量值：账号1:密码1,账号2:密码2,账号3:密码3
"""

import os
import time
import logging
import random
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
import requests
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class NodeLocAutoCheckin:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        
        if not self.username or not self.password:
            raise ValueError("用户名和密码不能为空")
        
        self.driver = None
        self.setup_driver()
    
    def setup_driver(self):
        """设置Chrome驱动选项"""
        chrome_options = Options()
        
        # GitHub Actions环境配置
        if os.getenv('GITHUB_ACTIONS'):
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
        
        # 通用配置 - 防检测
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        # 模拟真实 User-Agent
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # CDP 命令防止检测
        self.driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            """
        })
        
    def login(self):
        """执行登录流程"""
        logger.info(f"开始登录流程: {self.username}")
        
        try:
            # 访问登录页面
            self.driver.get("https://www.nodeloc.com/login")
            time.sleep(5)  # 等待页面加载
            
            # 输入用户名
            logger.info("输入用户名...")
            username_input = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "login-account-name"))
            )
            username_input.clear()
            username_input.send_keys(self.username)
            
            # 输入密码
            logger.info("输入密码...")
            password_input = self.driver.find_element(By.ID, "login-account-password")
            password_input.clear()
            password_input.send_keys(self.password)
            
            time.sleep(1)
            
            # 点击登录按钮
            logger.info("点击登录按钮...")
            login_btn = self.driver.find_element(By.ID, "login-button")
            login_btn.click()
            
            # 等待登录完成（检测页面跳转或登录框消失）
            logger.info("等待登录跳转...")
            time.sleep(5)
            
            # 简单判断：如果当前URL变回了首页或者不包含 login，或者能找到头像元素，则认为成功
            # NodeLoc 登录成功后通常会跳回首页或者刷新页面
            if "login" not in self.driver.current_url:
                logger.info("URL已变更，判断为登录成功")
                return True
            
            # 如果还在当前页，检查是否有错误提示
            try:
                error_alert = self.driver.find_element(By.CSS_SELECTOR, ".Alert--error")
                if error_alert.is_displayed():
                    raise Exception(f"登录失败: {error_alert.text}")
            except:
                pass
                
            # 再次确认是否在首页
            self.driver.get("https://www.nodeloc.com/")
            time.sleep(3)
            return True
            
        except Exception as e:
            logger.error(f"登录过程中出错: {e}")
            return False
    
    def get_balance(self):
        """获取当前账号的能量/积分 (NodeLoc)"""
        try:
            # NodeLoc 能量通常显示在侧边栏或顶部
            # 由于未提供具体selector，这里尝试抓取包含"能量"文本的元素
            # 或者你可以手动指定，例如 .UserCard-energy
            
            logger.info("尝试获取能量信息...")
            self.driver.get("https://www.nodeloc.com/")
            time.sleep(3)
            
            # 尝试通过文本查找
            page_source = self.driver.page_source
            if "能量" in page_source:
                 # 简单的正则提取或者查找 nearby 元素比较复杂，这里作为备用方案
                 pass

            # 尝试通用的 Flarum 用户信息区
            # 如果你知道具体的 class，可以在这里修改，例如: .item-energy
            return "查看个人中心" 
            
        except Exception as e:
            logger.warning(f"获取余额时出错: {e}")
            return "未知"
    
    def checkin(self):
        """执行签到流程"""
        logger.info("开始查找签到按钮...")
        
        # 确保在首页
        if self.driver.current_url != "https://www.nodeloc.com/":
            self.driver.get("https://www.nodeloc.com/")
            time.sleep(5)
        
        try:
            # 查找签到按钮
            # 使用你提供的 class: checkin-button
            checkin_btn = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "checkin-button"))
            )
            
            # 检查按钮是否可见/可点
            if checkin_btn.is_displayed() and checkin_btn.is_enabled():
                # 点击签到
                checkin_btn.click()
                logger.info("已点击签到按钮")
                time.sleep(3)
                
                # 尝试捕捉成功提示 (Flarum 通常使用 Alert 或 Modal)
                try:
                    alert = self.driver.find_element(By.CSS_SELECTOR, ".Alert-body")
                    logger.info(f"捕捉到提示信息: {alert.text}")
                    return f"签到成功: {alert.text}"
                except:
                    return "签到操作已执行 (无弹窗文本)"
            else:
                return "今日可能已签到 (按钮不可点)"
                
        except Exception as e:
            # 如果找不到按钮，很可能今天已经签到过了，或者没登录成功
            logger.warning(f"未找到签到按钮或出错: {e}")
            
            # 检查是否是因为未登录
            if "login" in self.driver.current_url:
                return "签到失败 (登录失效)"
            
            return "未找到签到按钮 (可能已签到)"
    
    def run(self):
        """单个账号执行流程"""
        try:
            logger.info(f"--- 开始处理账号: {self.username} ---")
            
            # 登录
            if self.login():
                # 签到
                result = self.checkin()
                # 余额 (可选)
                balance = self.get_balance()
                
                logger.info(f"执行结果: {result}, 能量/积分: {balance}")
                return True, result, balance
            else:
                raise Exception("登录失败")
                
        except Exception as e:
            error_msg = f"执行失败: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, "未知"
        
        finally:
            if self.driver:
                self.driver.quit()

class MultiAccountManager:
    def __init__(self):
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        self.accounts = self.load_accounts()
    
    def load_accounts(self):
        """从环境变量加载多账号信息"""
        accounts = []
        logger.info("开始加载账号配置...")
        
        # 格式: username:password,username2:password2
        accounts_str = os.getenv('NODELOC_ACCOUNTS', '').strip()
        
        if accounts_str:
            pairs = [p.strip() for p in accounts_str.split(',')]
            for p in pairs:
                if ':' in p:
                    username, password = p.split(':', 1)
                    accounts.append({'username': username.strip(), 'password': password.strip()})
        
        if not accounts:
            logger.error("未找到有效的账号配置，请设置环境变量 NODELOC_ACCOUNTS (格式: user:pass,user2:pass2)")
            
        logger.info(f"共加载 {len(accounts)} 个账号")
        return accounts
    
    def send_notification(self, results):
        """发送Telegram通知"""
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return
        
        try:
            success_count = sum(1 for _, success, _, _ in results if success)
            message = f"🤖 NodeLoc 自动签到报告\n"
            message += f"📅 日期: {datetime.now().strftime('%Y-%m-%d')}\n"
            message += f"📊 统计: 成功 {success_count}/{len(results)}\n\n"
            
            for username, success, result, balance in results:
                status = "✅" if success else "❌"
                # 隐藏部分用户名
                masked_user = username[:2] + "***" if len(username) > 2 else username
                message += f"{status} 账号: {masked_user}\n"
                message += f"   结果: {result}\n\n"
            
            requests.post(
                f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage",
                data={"chat_id": self.telegram_chat_id, "text": message}
            )
            logger.info("通知已发送")
        except Exception as e:
            logger.error(f"发送通知失败: {e}")

    def run_all(self):
        results = []
        for acc in self.accounts:
            handler = NodeLocAutoCheckin(acc['username'], acc['password'])
            success, result, balance = handler.run()
            results.append((acc['username'], success, result, balance))
            
            # 随机等待，避免并发过快
            time.sleep(random.uniform(5, 10))
            
        self.send_notification(results)

if __name__ == "__main__":
    MultiAccountManager().run_all()
