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
EXPERIENCE_DURATION_HOURS = 2  # 体验时长2小时

# 数据库初始化
def init_db():
    conn = sqlite3.connect('vip_experience.db')
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_experience (
            user_id INTEGER PRIMARY KEY,
            start_time TEXT,
            used INTEGER DEFAULT 0
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
# 注意：不使用 members intent（特权意图），改用 get_member() 从缓存获取
bot = commands.Bot(command_prefix='!', intents=intents)

# 错误处理：权限不足
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message('❌ 您没有权限使用此命令！', ephemeral=True)
    else:
        await interaction.response.send_message(f'❌ 发生错误：{str(error)}', ephemeral=True)
        raise error

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
            if role:
                member = guild.get_member(user_id)
                if member:
                    if role in member.roles:
                        # 用户还有身份组，需要移除
                        removed = await remove_expired_role(user_id, guild, role)
                        if removed:
                            await interaction.response.send_message(
                                '⏰ 您的体验时间已结束！身份组已自动移除。',
                                ephemeral=True
                            )
                        else:
                            await interaction.response.send_message(
                                '⏰ 您的体验时间已结束！但移除身份组时出错，请通知管理员。',
                                ephemeral=True
                            )
                    else:
                        # 用户已经没有身份组了
                        await interaction.response.send_message(
                            '⏰ 您的体验时间已结束！身份组已被移除。',
                            ephemeral=True
                        )
                else:
                    # 用户不在服务器中
                    await interaction.response.send_message(
                        '⏰ 您的体验时间已结束！',
                        ephemeral=True
                    )
            else:
                await interaction.response.send_message(
                    '⏰ 您的体验时间已结束！但找不到会员身份组，请通知管理员。',
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
        if member and role in member.roles:
            await member.remove_roles(role)
            print(f'已移除用户 {member.name} ({user_id}) 的体验权限')
            return True
    except Exception as e:
        print(f'移除用户 {user_id} 权限时出错：{str(e)}')
    return False

# 定时任务：检查并移除过期权限
@tasks.loop(minutes=1)
async def check_expired_roles():
    try:
        guild = bot.get_guild(GUILD_ID)
        if not guild:
            return
        
        role = guild.get_role(VIP_ROLE_ID)
        if not role:
            return
        
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
                await remove_expired_role(user_id, guild, role)
                # 注意：即使用户离开服务器，也不删除记录，确保每人只有一次机会
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
    
    embed.add_field(
        name='⏰ 体验时长',
        value=f'{EXPERIENCE_DURATION_HOURS}小时',
        inline=False
    )
    
    view = ExperienceView()
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name='help', description='显示所有可用指令')
async def help_command(interaction: discord.Interaction):
    """显示所有可用指令"""
    embed = discord.Embed(
        title='🤖 机器人指令帮助',
        description='以下是所有可用指令：',
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name='👤 用户指令',
        value=(
            '**按钮功能**（在体验申请面板中）：\n'
            '✨ **申请体验** - 申请体验会员权限（每人仅限一次）\n'
            '⏰ **查询时长** - 查看剩余体验时间\n\n'
            '**斜杠命令**：\n'
            '`/help` - 显示此帮助信息'
        ),
        inline=False
    )
    
    embed.add_field(
        name='👑 管理员指令',
        value=(
            '`/setup` - 发送体验权限申请面板\n'
            '`/checkall` - 查看所有体验用户信息'
        ),
        inline=False
    )
    
    embed.add_field(
        name='📝 使用说明',
        value=(
            '1. 管理员使用 `/setup` 发送体验申请面板\n'
            '2. 用户点击「申请体验」按钮申请权限\n'
            '3. 用户点击「查询时长」按钮查看剩余时间\n'
            '4. 体验时间结束后，权限会自动移除\n'
            '5. **重要**：每个用户只能获得一次体验机会，即使退出服务器重新加入也无法再次申请'
        ),
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

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
            if member:
                if role in member.roles:
                    # 用户有身份组，需要移除
                    if await remove_expired_role(user_id, guild, role):
                        removed_count += 1
                else:
                    # 用户没有身份组，可能已经被移除了
                    already_removed_count += 1
            else:
                # 用户不在服务器中
                print(f'用户 {user_id} 不在服务器中，但记录显示已过期')
    
    # 构建报告消息
    report_parts = [f'✅ 检查完成！', f'📊 检查了 {checked_count} 个用户']
    
    if expired_count > 0:
        report_parts.append(f'⏰ 发现 {expired_count} 个过期用户')
        if removed_count > 0:
            report_parts.append(f'🗑️ 移除了 {removed_count} 个过期权限')
        if already_removed_count > 0:
            report_parts.append(f'✅ {already_removed_count} 个用户的权限已被移除（可能之前已处理）')
    else:
        report_parts.append(f'✨ 没有发现过期权限')
    
    await interaction.followup.send('\n'.join(report_parts), ephemeral=True)

@bot.tree.command(name='sync', description='手动同步斜杠命令（仅管理员可用）')
@app_commands.checks.has_permissions(administrator=True)
async def sync_commands(interaction: discord.Interaction):
    """手动同步斜杠命令（仅管理员可用）"""
    await interaction.response.defer(ephemeral=True)
    
    try:
        # 如果有配置 GUILD_ID，同步到特定服务器（更快）
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            command_list = '\n'.join([f'  - /{cmd.name}: {cmd.description}' for cmd in synced])
            await interaction.followup.send(
                f'✅ 已同步 {len(synced)} 个斜杠命令到服务器！\n\n'
                f'**命令列表：**\n{command_list}\n\n'
                f'💡 现在可以在 Discord 中输入 `/` 查看这些命令了！',
                ephemeral=True
            )
        else:
            # 全局同步
            synced = await bot.tree.sync()
            command_list = '\n'.join([f'  - /{cmd.name}: {cmd.description}' for cmd in synced])
            await interaction.followup.send(
                f'✅ 已同步 {len(synced)} 个斜杠命令（全局）！\n\n'
                f'**命令列表：**\n{command_list}\n\n'
                f'⚠️ 注意：全局同步可能需要几分钟才能在所有服务器中生效',
                ephemeral=True
            )
    except Exception as e:
        await interaction.followup.send(
            f'❌ 同步命令时出错：{str(e)}',
            ephemeral=True
        )
        import traceback
        traceback.print_exc()

# 运行机器人
if __name__ == '__main__':
    if not TOKEN:
        print('错误：请在 .env 文件中设置 DISCORD_TOKEN')
    elif not GUILD_ID or not VIP_ROLE_ID:
        print('错误：请在 .env 文件中设置 GUILD_ID 和 VIP_ROLE_ID')
    else:
        bot.run(TOKEN)

