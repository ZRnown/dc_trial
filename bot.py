import discord
from discord import app_commands
from discord.ext import commands, tasks
import sqlite3
import asyncio
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置
TOKEN = os.getenv('DISCORD_TOKEN')
GUILD_ID = int(os.getenv('GUILD_ID', 0))
VIP_ROLE_ID = int(os.getenv('VIP_ROLE_ID', 0))
EXPERIENCE_DURATION_HOURS = 0.01  # 体验时长2小时

# 数据库初始化
def init_db():
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    
    # 体验会员表（保留原有功能）
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_experience (
            user_id INTEGER PRIMARY KEY,
            start_time TEXT,
            used INTEGER DEFAULT 0
        )
    ''')
    
    # 身份组配置表
    c.execute('''
        CREATE TABLE IF NOT EXISTS role_configs (
            role_id INTEGER PRIMARY KEY,
            role_name TEXT,
            duration_days INTEGER,
            created_at TEXT
        )
    ''')
    
    # 用户身份组记录表
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            role_id INTEGER,
            start_time TEXT,
            end_time TEXT,
            duration_days INTEGER,
            FOREIGN KEY (role_id) REFERENCES role_configs(role_id)
        )
    ''')
    
    conn.commit()
    conn.close()

# 获取用户信息
def get_user_info(user_id):
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('SELECT start_time, used FROM user_experience WHERE user_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result

# 保存用户信息
def save_user_info(user_id, start_time, used=0):
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO user_experience (user_id, start_time, used)
        VALUES (?, ?, ?)
    ''', (user_id, start_time, used))
    conn.commit()
    conn.close()

# 更新使用状态
def mark_as_used(user_id):
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('UPDATE user_experience SET used = 1 WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# 删除用户记录
def delete_user_info(user_id):
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('DELETE FROM user_experience WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

# ========== 身份组配置相关函数 ==========

# 添加身份组配置
def add_role_config(role_id, role_name, duration_days):
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO role_configs (role_id, role_name, duration_days, created_at)
        VALUES (?, ?, ?, ?)
    ''', (role_id, role_name, duration_days, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# 获取所有身份组配置
def get_all_role_configs():
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('SELECT role_id, role_name, duration_days FROM role_configs')
    results = c.fetchall()
    conn.close()
    return results

# 获取身份组配置
def get_role_config(role_id):
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('SELECT role_id, role_name, duration_days FROM role_configs WHERE role_id = ?', (role_id,))
    result = c.fetchone()
    conn.close()
    return result

# 删除身份组配置
def delete_role_config(role_id):
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('DELETE FROM role_configs WHERE role_id = ?', (role_id,))
    conn.commit()
    conn.close()

# ========== 用户身份组记录相关函数 ==========

# 添加用户身份组记录
def add_user_role(user_id, role_id, duration_days):
    start_time = datetime.now()
    end_time = start_time + timedelta(days=duration_days)
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('''
        INSERT INTO user_roles (user_id, role_id, start_time, end_time, duration_days)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, role_id, start_time.isoformat(), end_time.isoformat(), duration_days))
    conn.commit()
    conn.close()
    return end_time

# 获取用户的所有身份组记录
def get_user_roles(user_id):
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('''
        SELECT ur.id, ur.role_id, ur.start_time, ur.end_time, ur.duration_days, rc.role_name
        FROM user_roles ur
        LEFT JOIN role_configs rc ON ur.role_id = rc.role_id
        WHERE ur.user_id = ?
        ORDER BY ur.end_time DESC
    ''', (user_id,))
    results = c.fetchall()
    conn.close()
    return results

# 获取所有未过期的用户身份组记录
def get_all_active_user_roles():
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute('''
        SELECT ur.id, ur.user_id, ur.role_id, ur.start_time, ur.end_time, ur.duration_days, rc.role_name
        FROM user_roles ur
        LEFT JOIN role_configs rc ON ur.role_id = rc.role_id
        WHERE ur.end_time > ?
        ORDER BY ur.end_time ASC
    ''', (now,))
    results = c.fetchall()
    conn.close()
    return results

# 删除用户身份组记录
def delete_user_role(record_id):
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('DELETE FROM user_roles WHERE id = ?', (record_id,))
    conn.commit()
    conn.close()

# 计算剩余时间
def get_remaining_time(start_time_str):
    if not start_time_str:
        return None
    start_time = datetime.fromisoformat(start_time_str)
    end_time = start_time + timedelta(hours=EXPERIENCE_DURATION_HOURS)
    now = datetime.now()
    if now >= end_time:
        return None  # 已过期
    remaining = end_time - now
    return remaining

# 创建机器人
intents = discord.Intents.default()
intents.message_content = True
intents.members = True  # 必须开启，机器人才能在后台看到所有成员
bot = commands.Bot(command_prefix='!', intents=intents)

# 错误处理：权限不足
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    try:
        if isinstance(error, app_commands.MissingPermissions):
            if not interaction.response.is_done():
                await interaction.response.send_message('❌ 您没有权限使用此命令！', ephemeral=True)
            else:
                await interaction.followup.send('❌ 您没有权限使用此命令！', ephemeral=True)
        else:
            # 检查交互是否已经响应
            if not interaction.response.is_done():
                await interaction.response.send_message(f'❌ 发生错误：{str(error)}', ephemeral=True)
            else:
                # 如果已经响应过，使用 followup
                await interaction.followup.send(f'❌ 发生错误：{str(error)}', ephemeral=True)
    except discord.errors.NotFound:
        # 交互已过期，无法响应
        print(f'⚠️ 交互已过期，无法发送错误消息：{str(error)}')
    except Exception as e:
        print(f'❌ 错误处理时发生异常：{str(e)}')
        import traceback
        traceback.print_exc()

# 翻页视图
class PaginatedView(discord.ui.View):
    def __init__(self, pages, initial_page=0):
        super().__init__(timeout=300)  # 5分钟超时
        self.pages = pages
        self.current_page = initial_page
        self.max_page = len(pages) - 1
        self.update_buttons()
    
    def update_buttons(self):
        # 清除所有按钮
        self.clear_items()
        
        # 上一页按钮
        prev_button = discord.ui.Button(
            label='上一页',
            style=discord.ButtonStyle.primary,
            emoji='◀️',
            disabled=self.current_page == 0
        )
        prev_button.callback = self.previous_page
        self.add_item(prev_button)
        
        # 页码显示
        page_button = discord.ui.Button(
            label=f'{self.current_page + 1}/{self.max_page + 1}',
            style=discord.ButtonStyle.secondary,
            disabled=True
        )
        self.add_item(page_button)
        
        # 下一页按钮
        next_button = discord.ui.Button(
            label='下一页',
            style=discord.ButtonStyle.primary,
            emoji='▶️',
            disabled=self.current_page >= self.max_page
        )
        next_button.callback = self.next_page
        self.add_item(next_button)
    
    async def previous_page(self, interaction: discord.Interaction):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)
    
    async def next_page(self, interaction: discord.Interaction):
        if self.current_page < self.max_page:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.pages[self.current_page], view=self)

# 按钮视图
class ExperienceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    
    @discord.ui.button(label='申请体验', style=discord.ButtonStyle.primary, emoji='✨')
    async def apply_experience(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        user_info = get_user_info(user_id)
        
        # 检查是否已经使用过
        if user_info and user_info[1] == 1:
            await interaction.response.send_message(
                '❌ 您已经使用过体验机会了，每个会员只能获得一次体验机会！',
                ephemeral=True
            )
            return
        
        # 检查是否正在体验中
        if user_info and user_info[0]:
            remaining = get_remaining_time(user_info[0])
            if remaining:
                total_seconds = int(remaining.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                await interaction.response.send_message(
                    f'⚠️ 您正在体验中，剩余时间：{hours}小时{minutes}分钟',
                    ephemeral=True
                )
                return
        
        # 赋予身份组
        guild = interaction.guild
        role = guild.get_role(VIP_ROLE_ID)
        if not role:
            await interaction.response.send_message(
                '❌ 错误：找不到会员身份组，请检查配置！',
                ephemeral=True
            )
            return
        
        try:
            await interaction.user.add_roles(role)
            start_time = datetime.now().isoformat()
            save_user_info(user_id, start_time, used=1)
            
            await interaction.response.send_message(
                f'✅ 体验权限已激活！\n'
                f'⏰ 体验时长：{EXPERIENCE_DURATION_HOURS}小时\n'
                f'📅 到期时间：{(datetime.now() + timedelta(hours=EXPERIENCE_DURATION_HOURS)).strftime("%Y-%m-%d %H:%M:%S")}\n'
                f'⚠️ 时间结束后，权限将自动移除',
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                '❌ 错误：机器人没有权限赋予身份组！',
                ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f'❌ 发生错误：{str(e)}',
                ephemeral=True
            )
    
    @discord.ui.button(label='查询时长', style=discord.ButtonStyle.secondary, emoji='⏰')
    async def check_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        user_info = get_user_info(user_id)
        
        if not user_info or not user_info[0]:
            await interaction.response.send_message(
                '❌ 您还没有申请体验权限！',
                ephemeral=True
            )
            return
        
        remaining = get_remaining_time(user_info[0])
        if not remaining:
            # 如果已过期，立即移除身份组
            guild = interaction.guild
            role = guild.get_role(VIP_ROLE_ID)
            if not role:
                await interaction.response.send_message(
                    '⏰ 您的体验时间已结束！但找不到会员身份组，请通知管理员。',
                    ephemeral=True
                )
                return
            
            member = guild.get_member(user_id)
            if not member:
                await interaction.response.send_message(
                    '⏰ 您的体验时间已结束！',
                    ephemeral=True
                )
                return
            
            if role not in member.roles:
                # 用户已经没有身份组了
                await interaction.response.send_message(
                    '⏰ 您的体验时间已结束！身份组已被移除。',
                    ephemeral=True
                )
                return
            
            # 用户还有身份组，需要移除
            try:
                await member.remove_roles(role)
                print(f'✅ [查询时长] 已移除用户 {member.name} ({user_id}) 的体验权限')
                await interaction.response.send_message(
                    '⏰ 您的体验时间已结束！身份组已自动移除。',
                    ephemeral=True
                )
            except discord.Forbidden:
                print(f'❌ [查询时长] 权限不足：无法移除用户 {member.name} ({user_id}) 的身份组')
                print(f'   提示：确保机器人的身份组在服务器身份组列表中位于会员身份组之上')
                await interaction.response.send_message(
                    '⏰ 您的体验时间已结束！\n'
                    '❌ 但移除身份组时权限不足，请通知管理员检查机器人权限。',
                    ephemeral=True
                )
            except Exception as e:
                print(f'❌ [查询时长] 移除用户 {member.name} ({user_id}) 权限时出错：{str(e)}')
                import traceback
                traceback.print_exc()
                await interaction.response.send_message(
                    f'⏰ 您的体验时间已结束！\n'
                    f'❌ 但移除身份组时出错：{str(e)}\n'
                    f'请通知管理员。',
                    ephemeral=True
                )
        else:
            total_seconds = int(remaining.total_seconds())
            hours = total_seconds // 3600
            minutes = (total_seconds % 3600) // 60
            seconds = total_seconds % 60
            start_time = datetime.fromisoformat(user_info[0])
            end_time = start_time + timedelta(hours=EXPERIENCE_DURATION_HOURS)
            
            await interaction.response.send_message(
                f'⏰ **剩余体验时间**\n'
                f'📅 开始时间：{start_time.strftime("%Y-%m-%d %H:%M:%S")}\n'
                f'📅 到期时间：{end_time.strftime("%Y-%m-%d %H:%M:%S")}\n'
                f'⏳ 剩余时长：{hours}小时{minutes}分钟{seconds}秒',
                ephemeral=True
            )

# 移除单个用户的过期权限
async def remove_expired_role(user_id, guild, role):
    """移除单个用户的过期权限"""
    try:
        member = guild.get_member(user_id)
        if not member:
            print(f'用户 {user_id} 不在服务器中')
            return False
        
        if role not in member.roles:
            print(f'用户 {member.name} ({user_id}) 没有该身份组')
            return False
        
        await member.remove_roles(role)
        print(f'✅ 已移除用户 {member.name} ({user_id}) 的体验权限')
        return True
    except discord.Forbidden as e:
        print(f'❌ 权限不足：无法移除用户 {user_id} 的身份组 - {str(e)}')
        print(f'   提示：确保机器人的身份组在服务器身份组列表中位于会员身份组之上')
        return False
    except discord.HTTPException as e:
        print(f'❌ HTTP错误：移除用户 {user_id} 权限时出错 - {str(e)}')
        return False
    except Exception as e:
        print(f'❌ 未知错误：移除用户 {user_id} 权限时出错 - {str(e)}')
        import traceback
        traceback.print_exc()
        return False

# 定时任务：检查并移除过期权限
@tasks.loop(minutes=1)
async def check_expired_roles():
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            return
        
        # 检查体验会员（原有功能）
        if VIP_ROLE_ID:
            role = guild.get_role(VIP_ROLE_ID)
            if role:
                conn = sqlite3.connect('vip_experience.db')
                c = conn.cursor()
                c.execute('SELECT user_id, start_time FROM user_experience WHERE used = 1')
                users = c.fetchall()
                conn.close()
                
                for user_id, start_time_str in users:
                    if not start_time_str:
                        continue
                    
                    remaining = get_remaining_time(start_time_str)
                    if remaining is None:  # 已过期
                        # 先从缓存获取
                        member = guild.get_member(user_id)
                        if member is None:
                            try:
                                # 如果缓存里没有，尝试从API获取（兜底方案）
                                member = await guild.fetch_member(user_id)
                            except discord.NotFound:
                                print(f'⚠️ 用户 {user_id} 已离开服务器，跳过移除')
                                continue
                            except Exception as e:
                                print(f'❌ 获取用户 {user_id} 失败: {e}')
                                continue
                        
                        # 此时 member 一定不为 None
                        if role in member.roles:
                            try:
                                await member.remove_roles(role)
                                print(f'✅ [定时任务] 已移除用户 {member.name} ({user_id}) 的体验权限')
                            except discord.Forbidden:
                                print(f'❌ [定时任务] 权限不足：无法移除用户 {member.name} ({user_id}) 的身份组')
                            except Exception as e:
                                print(f'❌ [定时任务] 移除用户 {member.name} ({user_id}) 权限时出错：{str(e)}')
        
        # 检查手动赋予的身份组
        active_roles = get_all_active_user_roles()
        now = datetime.now()
        
        for record in active_roles:
            record_id, user_id, role_id, start_time_str, end_time_str, duration_days, role_name = record
            end_time = datetime.fromisoformat(end_time_str)
            
            if now >= end_time:  # 已过期
                try:
                    role_obj = guild.get_role(role_id)
                    if not role_obj:
                        # 身份组不存在，删除记录
                        delete_user_role(record_id)
                        print(f'身份组 {role_id} 不存在，已删除记录（记录ID: {record_id}）')
                        continue
                    
                    # 先从缓存获取
                    member = guild.get_member(user_id)
                    if member is None:
                        try:
                            # 如果缓存里没有，尝试从API获取（兜底方案）
                            member = await guild.fetch_member(user_id)
                        except discord.NotFound:
                            # 用户已离开服务器，删除记录
                            delete_user_role(record_id)
                            print(f'用户 {user_id} 已离开服务器，已删除记录（记录ID: {record_id}）')
                            continue
                        except Exception as e:
                            print(f'❌ 获取用户 {user_id} 失败: {e}')
                            continue
                    
                    # 此时 member 一定不为 None
                    if role_obj in member.roles:
                        try:
                            await member.remove_roles(role_obj)
                            delete_user_role(record_id)
                            print(f'✅ [定时任务] 已移除用户 {member.name} ({user_id}) 的身份组 {role_name or role_id}（记录ID: {record_id}）')
                        except discord.Forbidden:
                            print(f'❌ [定时任务] 权限不足：无法移除用户 {member.name} ({user_id}) 的身份组 {role_id}')
                        except Exception as e:
                            print(f'❌ [定时任务] 移除用户 {member.name} ({user_id}) 身份组 {role_id} 时出错：{str(e)}')
                    else:
                        # 用户没有身份组，删除记录
                        delete_user_role(record_id)
                        print(f'用户 {member.name} ({user_id}) 没有身份组 {role_id}，已删除记录（记录ID: {record_id}）')
                except Exception as e:
                    print(f'❌ 处理用户 {user_id} 身份组 {role_id} 时出错：{str(e)}')
                    import traceback
                    traceback.print_exc()
    except Exception as e:
        print(f'检查过期权限时出错：{str(e)}')

@bot.event
async def on_ready():
    print(f'{bot.user} 已上线！')
    init_db()
    check_expired_roles.start()
    print('定时任务已启动')
    
    # 同步斜杠命令
    try:
        # 如果有配置 GUILD_ID，先同步到特定服务器（更快）
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f'已同步 {len(synced)} 个斜杠命令到服务器 {GUILD_ID}')
            for cmd in synced:
                print(f'  - /{cmd.name}: {cmd.description}')
        else:
            # 全局同步（可能需要几分钟才能生效）
            synced = await bot.tree.sync()
            print(f'已同步 {len(synced)} 个斜杠命令（全局）')
            print('注意：全局同步可能需要几分钟才能在所有服务器中生效')
            for cmd in synced:
                print(f'  - /{cmd.name}: {cmd.description}')
    except Exception as e:
        print(f'同步斜杠命令时出错：{e}')
        import traceback
        traceback.print_exc()

@bot.tree.command(name='setup', description='发送体验权限申请面板（仅管理员可用）')
@app_commands.checks.has_permissions(administrator=True)
async def setup_experience(interaction: discord.Interaction):
    """发送体验权限申请消息（仅管理员可用）"""
    embed = discord.Embed(
        title='✨ 体验权限申请 ✨',
        description='点击下方按钮申请体验权限。',
        color=discord.Color.gold()
    )
    
    embed.add_field(
        name='⚠️ 注意事项',
        value=(
            '➡️ 每个会员可以获得一次体验机会\n'
            '➡️ 体验会员可以体验部分频道\n'
            '➡️ 体验时间结束后，权限将自动移除\n'
            '➡️ 点击「查询时长」按钮可查看剩余会员时间'
        ),
        inline=False
    )
    
    # 计算体验时长显示
    if EXPERIENCE_DURATION_HOURS < 1:
        duration_minutes = int(EXPERIENCE_DURATION_HOURS * 60)
        duration_display = f'{duration_minutes}分钟'
    else:
        duration_display = f'{EXPERIENCE_DURATION_HOURS}小时'
    
    embed.add_field(
        name='⏰ 体验时长',
        value=duration_display,
        inline=False
    )
    
    view = ExperienceView()
    try:
        await interaction.response.send_message(embed=embed, view=view)
    except discord.errors.NotFound:
        # 交互已过期
        print('⚠️ setup 命令：交互已过期，无法发送消息')
    except Exception as e:
        print(f'❌ setup 命令出错：{str(e)}')
        import traceback
        traceback.print_exc()

@bot.tree.command(name='checkall', description='查看所有体验用户信息（仅管理员可用）')
@app_commands.checks.has_permissions(administrator=True)
async def check_all_users(interaction: discord.Interaction):
    """查看所有体验用户信息（仅管理员可用）"""
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('SELECT user_id, start_time, used FROM user_experience WHERE used = 1')
    users = c.fetchall()
    conn.close()
    
    if not users:
        await interaction.response.send_message('📋 当前没有体验用户')
        return
    
    embed = discord.Embed(title='📋 体验用户列表', color=discord.Color.blue())
    guild = interaction.guild
    
    for user_id, start_time_str, used in users:
        member = guild.get_member(user_id)
        if member:
            username = member.display_name
        else:
            username = f'用户ID: {user_id} (不在服务器或不在缓存中)'
        
        if start_time_str:
            remaining = get_remaining_time(start_time_str)
            if remaining:
                total_seconds = int(remaining.total_seconds())
                hours = total_seconds // 3600
                minutes = (total_seconds % 3600) // 60
                status = f'⏳ 剩余 {hours}小时{minutes}分钟'
            else:
                status = '⏰ 已过期'
        else:
            status = '❌ 无开始时间'
        
        embed.add_field(
            name=username,
            value=f'开始时间: {start_time_str or "无"}\n状态: {status}',
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='checkexpired', description='立即检查并移除所有过期的体验权限（仅管理员可用）')
@app_commands.checks.has_permissions(administrator=True)
async def check_expired_now(interaction: discord.Interaction):
    """立即检查并移除所有过期的体验权限（仅管理员可用）"""
    await interaction.response.defer(ephemeral=True)
    
    guild = interaction.guild
    if not guild:
        await interaction.followup.send('❌ 无法获取服务器信息', ephemeral=True)
        return
    
    role = guild.get_role(VIP_ROLE_ID)
    if not role:
        await interaction.followup.send('❌ 找不到会员身份组，请检查配置！', ephemeral=True)
        return
    
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('SELECT user_id, start_time FROM user_experience WHERE used = 1')
    users = c.fetchall()
    conn.close()
    
    removed_count = 0
    expired_count = 0
    checked_count = 0
    already_removed_count = 0
    
    for user_id, start_time_str in users:
        if not start_time_str:
            continue
        
        checked_count += 1
        remaining = get_remaining_time(start_time_str)
        if remaining is None:  # 已过期
            expired_count += 1
            member = guild.get_member(user_id)
            
            # 检查是否是服务器所有者
            is_owner = guild.owner_id == user_id if guild.owner_id else False
            
            if member:
                if role in member.roles:
                    # 用户有身份组，需要移除
                    if is_owner:
                        # 服务器所有者无法移除身份组（Discord限制）
                        print(f'⚠️ 用户 {member.name} ({user_id}) 是服务器所有者，无法自动移除身份组（Discord限制）')
                        # 标记为已处理（虽然实际上无法移除）
                        already_removed_count += 1
                    else:
                        # 直接尝试移除
                        try:
                            await member.remove_roles(role)
                            removed_count += 1
                            print(f'✅ [checkexpired] 已移除用户 {member.name} ({user_id}) 的体验权限')
                        except discord.Forbidden:
                            print(f'❌ [checkexpired] 权限不足：无法移除用户 {member.name} ({user_id}) 的身份组')
                            print(f'   提示：确保机器人的身份组在服务器身份组列表中位于会员身份组之上')
                        except Exception as e:
                            print(f'❌ [checkexpired] 移除用户 {member.name} ({user_id}) 权限时出错：{str(e)}')
                else:
                    # 用户没有身份组，可能已经被移除了
                    already_removed_count += 1
                    print(f'用户 {member.name} ({user_id}) 的身份组已被移除')
            elif is_owner:
                # 服务器所有者可能不在缓存中，但我们可以检测到
                print(f'⚠️ 用户 {user_id} 是服务器所有者，无法自动移除身份组（Discord限制）')
                already_removed_count += 1
            else:
                # 用户不在服务器中或不在缓存中
                print(f'⚠️ 用户 {user_id} 不在服务器缓存中，但记录显示已过期')
                print(f'   提示：用户可能已离开服务器，或者需要启用 members intent 才能检测')
    
    # 构建报告消息
    report_parts = [f'✅ 检查完成！', f'📊 检查了 {checked_count} 个用户']
    
    if expired_count > 0:
        report_parts.append(f'⏰ 发现 {expired_count} 个过期用户')
        if removed_count > 0:
            report_parts.append(f'🗑️ 移除了 {removed_count} 个过期权限')
        if already_removed_count > 0:
            report_parts.append(f'✅ {already_removed_count} 个用户的权限已被移除（可能之前已处理）')
        
        # 如果有过期用户但没有成功移除，说明有问题
        failed_count = expired_count - removed_count - already_removed_count
        if failed_count > 0:
            report_parts.append(f'')
            report_parts.append(f'⚠️ **警告**：有 {failed_count} 个过期用户的权限未能移除！')
            report_parts.append(f'可能的原因：')
            report_parts.append(f'1. 机器人的身份组位置低于会员身份组')
            report_parts.append(f'2. 机器人没有"管理身份组"权限')
            report_parts.append(f'3. 用户不在服务器缓存中')
            report_parts.append(f'')
            report_parts.append(f'💡 可以使用 `/removeuser <用户ID>` 命令删除该用户的记录')
    else:
        report_parts.append(f'✨ 没有发现过期权限')
    
    await interaction.followup.send('\n'.join(report_parts), ephemeral=True)

# ========== 身份组管理命令 ==========

@bot.tree.command(name='addrole', description='添加身份组配置（仅管理员可用）')
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(role='要配置的身份组', days='有效期天数')
async def add_role_config_cmd(interaction: discord.Interaction, role: discord.Role, days: int):
    """添加身份组配置"""
    if days <= 0:
        await interaction.response.send_message('❌ 天数必须大于0！', ephemeral=True)
        return
    
    add_role_config(role.id, role.name, days)
    await interaction.response.send_message(
        f'✅ 已添加身份组配置：\n'
        f'身份组：{role.mention} ({role.name})\n'
        f'有效期：{days} 天',
        ephemeral=True
    )

@bot.tree.command(name='listroles', description='查看所有身份组配置（仅管理员可用）')
@app_commands.checks.has_permissions(administrator=True)
async def list_role_configs_cmd(interaction: discord.Interaction):
    """查看所有身份组配置"""
    configs = get_all_role_configs()
    
    if not configs:
        await interaction.response.send_message('📋 当前没有配置的身份组', ephemeral=True)
        return
    
    embed = discord.Embed(title='📋 身份组配置列表', color=discord.Color.blue())
    guild = interaction.guild
    
    for role_id, role_name, duration_days in configs:
        role = guild.get_role(role_id)
        if role:
            role_mention = role.mention
        else:
            role_mention = f'身份组已删除 (ID: {role_id})'
        
        embed.add_field(
            name=role_name or f'ID: {role_id}',
            value=f'身份组: {role_mention}\n有效期: {duration_days} 天',
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='removerole', description='删除身份组配置（仅管理员可用）')
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(role='要删除配置的身份组')
async def remove_role_config_cmd(interaction: discord.Interaction, role: discord.Role):
    """删除身份组配置"""
    config = get_role_config(role.id)
    if not config:
        await interaction.response.send_message(f'❌ 身份组 {role.mention} 没有配置', ephemeral=True)
        return
    
    delete_role_config(role.id)
    await interaction.response.send_message(
        f'✅ 已删除身份组配置：{role.mention}',
        ephemeral=True
    )

@bot.tree.command(name='givemember', description='赋予用户身份组（仅管理员可用）')
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member='要赋予身份组的用户', role='要赋予的身份组', days='有效期天数（可选，默认使用配置）')
async def give_member_role_cmd(interaction: discord.Interaction, member: discord.Member, role: discord.Role, days: int = None):
    """赋予用户身份组"""
    # 检查身份组是否已配置
    config = get_role_config(role.id)
    if not config and days is None:
        await interaction.response.send_message(
            f'❌ 身份组 {role.mention} 未配置！\n'
            f'请先使用 `/addrole` 配置身份组，或在此命令中指定天数。',
            ephemeral=True
        )
        return
    
    # 确定天数
    if days is None:
        duration_days = config[2]  # 使用配置的天数
    else:
        if days <= 0:
            await interaction.response.send_message('❌ 天数必须大于0！', ephemeral=True)
            return
        duration_days = days
    
    try:
        # 赋予身份组
        await member.add_roles(role)
        
        # 记录到数据库
        end_time = add_user_role(member.id, role.id, duration_days)
        
        await interaction.response.send_message(
            f'✅ 已赋予用户 {member.mention} 身份组 {role.mention}\n'
            f'⏰ 有效期：{duration_days} 天\n'
            f'📅 到期时间：{end_time.strftime("%Y-%m-%d %H:%M:%S")}',
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message(
            '❌ 错误：机器人没有权限赋予身份组！',
            ephemeral=True
        )
    except Exception as e:
        await interaction.response.send_message(
            f'❌ 发生错误：{str(e)}',
            ephemeral=True
        )

@bot.tree.command(name='checkmember', description='查看用户的所有身份组记录（仅管理员可用）')
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(member='要查看的用户')
async def check_member_roles_cmd(interaction: discord.Interaction, member: discord.Member):
    """查看用户的所有身份组记录"""
    records = get_user_roles(member.id)
    
    if not records:
        await interaction.response.send_message(
            f'📋 用户 {member.mention} 没有身份组记录',
            ephemeral=True
        )
        return
    
    embed = discord.Embed(
        title=f'📋 {member.display_name} 的身份组记录',
        color=discord.Color.blue()
    )
    
    for record in records:
        record_id, role_id, start_time_str, end_time_str, duration_days, role_name = record
        start_time = datetime.fromisoformat(start_time_str)
        end_time = datetime.fromisoformat(end_time_str)
        now = datetime.now()
        
        role = interaction.guild.get_role(role_id)
        if role:
            role_display = role.mention
        else:
            role_display = f'身份组已删除 (ID: {role_id})'
        
        if now >= end_time:
            status = '⏰ 已过期'
        else:
            remaining = end_time - now
            days = remaining.days
            hours = remaining.seconds // 3600
            status = f'⏳ 剩余 {days}天{hours}小时'
        
        embed.add_field(
            name=f'{role_name or f"ID: {role_id}"} (记录ID: {record_id})',
            value=(
                f'身份组: {role_display}\n'
                f'开始: {start_time.strftime("%Y-%m-%d %H:%M:%S")}\n'
                f'到期: {end_time.strftime("%Y-%m-%d %H:%M:%S")}\n'
                f'状态: {status}'
            ),
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name='listmembers', description='查看所有有身份组记录的用户（仅管理员可用）')
@app_commands.checks.has_permissions(administrator=True)
async def list_members_with_roles_cmd(interaction: discord.Interaction):
    """查看所有有身份组记录的用户"""
    await interaction.response.defer(ephemeral=True)
    
    active_roles = get_all_active_user_roles()
    
    if not active_roles:
        await interaction.followup.send('📋 当前没有活跃的身份组记录', ephemeral=True)
        return
    
    guild = interaction.guild
    
    # 按用户分组
    user_records = {}
    for record in active_roles:
        record_id, user_id, role_id, start_time_str, end_time_str, duration_days, role_name = record
        if user_id not in user_records:
            user_records[user_id] = []
        user_records[user_id].append(record)
    
    # 转换为列表并按用户ID排序
    user_list = list(user_records.items())
    user_list.sort(key=lambda x: x[0])
    
    # 每页显示10个用户（Discord embed最多25个字段，留一些余量）
    items_per_page = 10
    total_pages = (len(user_list) + items_per_page - 1) // items_per_page
    
    # 生成所有页面
    pages = []
    for page_num in range(total_pages):
        start_idx = page_num * items_per_page
        end_idx = min(start_idx + items_per_page, len(user_list))
        
        embed = discord.Embed(
            title='📋 活跃身份组记录',
            description=f'共 {len(user_list)} 个用户',
            color=discord.Color.blue()
        )
        
        for user_id, records in user_list[start_idx:end_idx]:
            member = guild.get_member(user_id)
            if member:
                username = member.display_name
            else:
                username = f'用户ID: {user_id}'
            
            roles_info = []
            for record in records:
                record_id, _, role_id, _, end_time_str, _, role_name = record
                end_time = datetime.fromisoformat(end_time_str)
                remaining = end_time - datetime.now()
                days = remaining.days
                hours = remaining.seconds // 3600
                
                role = guild.get_role(role_id)
                if role:
                    role_display = role.name
                else:
                    role_display = f'ID: {role_id}'
                
                roles_info.append(f'{role_display}: 剩余{days}天{hours}小时')
            
            embed.add_field(
                name=username,
                value='\n'.join(roles_info) if roles_info else '无身份组信息',
                inline=False
            )
        
        embed.set_footer(text=f'第 {page_num + 1} 页，共 {total_pages} 页')
        pages.append(embed)
    
    # 发送第一页
    if total_pages > 1:
        view = PaginatedView(pages, initial_page=0)
        await interaction.followup.send(embed=pages[0], view=view, ephemeral=True)
    else:
        await interaction.followup.send(embed=pages[0], ephemeral=True)

# 运行机器人
if __name__ == '__main__':
    if not TOKEN:
        print('错误：请在 .env 文件中设置 DISCORD_TOKEN')
    elif not GUILD_ID or not VIP_ROLE_ID:
        print('错误：请在 .env 文件中设置 GUILD_ID 和 VIP_ROLE_ID')
    else:
        bot.run(TOKEN)

