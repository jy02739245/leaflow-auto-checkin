#!/usr/bin/env python3
"""
NodeLoc 多账号自动签到脚本
环境变量：
NODELOC_ACCOUNTS: 账号:密码,账号2:密码2
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
            chrome_options.add_argument('--headless=new')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
        
        # 通用配置 - 防检测
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
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
            self.driver.get("https://www.nodeloc.com/login")
            time.sleep(5)
            
            username_input = WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.ID, "login-account-name"))
            )
            username_input.clear()
            username_input.send_keys(self.username)
            
            password_input = self.driver.find_element(By.ID, "login-account-password")
            password_input.clear()
            password_input.send_keys(self.password)
            
            time.sleep(1)
            self.driver.find_element(By.ID, "login-button").click()
            
            time.sleep(5)
            if "login" not in self.driver.current_url:
                logger.info("登录成功")
                return True
            
            self.driver.get("https://www.nodeloc.com/")
            time.sleep(3)
            return True
            
        except Exception as e:
            logger.error(f"登录出错: {e}")
            return False
    
    def checkin(self):
        """执行签到流程"""
        logger.info("检查签到状态...")
        if self.driver.current_url != "https://www.nodeloc.com/":
            self.driver.get("https://www.nodeloc.com/")
            time.sleep(5)
        
        try:
            checkin_btn = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.CLASS_NAME, "checkin-button"))
            )
            
            if checkin_btn.is_displayed() and checkin_btn.is_enabled():
                checkin_btn.click()
                logger.info("已点击签到按钮")
                time.sleep(3)
                return True
            else:
                logger.info("签到按钮不可用")
                return False 
        except:
            logger.info("未找到签到按钮，可能已签到")
            return False

    def get_points_info(self):
        """获取积分详情 - 严格匹配模式"""
        try:
            logger.info("等待2秒后获取积分详情...")
            time.sleep(2)
            
            # 尝试动态获取积分页面URL
            try:
                avatar_link = self.driver.find_element(By.CSS_SELECTOR, ".App-header-controls .Avatar").find_element(By.XPATH, "./..").get_attribute("href")
                points_url = f"{avatar_link}/points-history/events"
            except:
                points_url = f"https://www.nodeloc.com/u/{self.username}/points-history/events"
            
            logger.info(f"访问积分页面: {points_url}")
            self.driver.get(points_url)
            time.sleep(5)
            
            # 1. 获取总能量
            total_points = "未知"
            try:
                total_elem = self.driver.find_element(By.CSS_SELECTOR, ".total-scores .value")
                total_points = total_elem.text.strip()
            except:
                logger.warning("未找到总能量元素")

            # 2. 获取今日签到奖励
            today_reward = "未知"
            checkin_time = "未知"
            
            try:
                # 找到所有增加积分的行
                positive_rows = self.driver.find_elements(By.CSS_SELECTOR, "tr.positive-points")
                
                if positive_rows:
                    # 只检查第一行 (最新的记录)
                    first_row = positive_rows[0]
                    cols = first_row.find_elements(By.TAG_NAME, "td")
                    
                    if len(cols) >= 3:
                        # 第三列 (索引2) 是原因列
                        reason_text = cols[2].text.strip()
                        logger.info(f"最新一条正向积分记录原因: {reason_text}")
                        
                        # 只有当原因是"每日签到奖励"时才提取
                        if "每日签到奖励" in reason_text:
                            # 第二列 (索引1) 是分数
                            score_span = cols[1].find_element(By.CSS_SELECTOR, ".positive")
                            today_reward = score_span.text.strip()
                            
                            # 第一列 (索引0) 是时间
                            time_span = cols[0].find_element(By.TAG_NAME, "span")
                            checkin_time = time_span.get_attribute("title")
                            
                            logger.info(f"成功提取签到奖励: {today_reward}")
                        else:
                            logger.info("最新一条记录不是签到奖励，跳过提取")
            except Exception as e:
                logger.warning(f"提取表格数据时出错: {e}")
            
            return {
                "total": total_points,
                "reward": today_reward,
                "time": checkin_time
            }
            
        except Exception as e:
            logger.error(f"获取积分详情失败: {e}")
            return None

    def run(self):
        try:
            logger.info(f"--- 开始处理账号: {self.username} ---")
            if self.login():
                # 尝试签到
                self.checkin()
                
                # 获取积分信息
                info = self.get_points_info()
                
                if info:
                    if info['reward'] != "未知":
                        result_msg = f"签到成功，您获得了 {info['reward']} 能量"
                    else:
                        result_msg = "今日已签到 (无今日新增记录)"
                        
                    balance_msg = info['total']
                else:
                    result_msg = "签到完成 (无法获取详情)"
                    balance_msg = "未知"
                
                logger.info(f"{result_msg}, 总能量: {balance_msg}")
                return True, result_msg, balance_msg
            else:
                raise Exception("登录失败")
        except Exception as e:
            return False, f"执行异常: {str(e)}", "未知"
        finally:
            if self.driver:
                self.driver.quit()

class MultiAccountManager:
    def __init__(self):
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        self.accounts = self.load_accounts()
    
    def load_accounts(self):
        accounts = []
        accounts_str = os.getenv('NODELOC_ACCOUNTS', '').strip()
        if accounts_str:
            pairs = [p.strip() for p in accounts_str.split(',')]
            for p in pairs:
                if ':' in p:
                    u, pw = p.split(':', 1)
                    accounts.append({'username': u.strip(), 'password': pw.strip()})
        return accounts
    
    def send_notification(self, results):
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return
        
        message = ""
        for username, success, result, balance in results:
            masked_user = username[:2] + "***"
            if success:
                message += f"✅ 账号：{masked_user}\n"
                message += f"{result}\n"
                message += f"💰 当前总能量：{balance}\n\n"
            else:
                message += f"❌ 账号：{masked_user}\n"
                message += f"执行失败: {result}\n\n"
        
        if message:
            requests.post(
                f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage",
                data={"chat_id": self.telegram_chat_id, "text": message}
            )

    def run_all(self):
        results = []
        for acc in self.accounts:
            handler = NodeLocAutoCheckin(acc['username'], acc['password'])
            success, result, balance = handler.run()
            results.append((acc['username'], success, result, balance))
            time.sleep(random.uniform(3, 8))
        self.send_notification(results)

if __name__ == "__main__":
    MultiAccountManager().run_all()
