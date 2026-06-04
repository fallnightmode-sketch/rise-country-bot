import sys
import subprocess
import re
import os
import json
from datetime import datetime

# ====================================================================
# URUTAN IMPORT DISCORD WAJIB BERADA DI PALING ATAS
# ====================================================================
import discord
from discord.ext import commands, tasks

# ====================================================================
# AUTO-INSTALLER GUARD WITH pytz FOR TIMEZONE CONTROL
# ====================================================================
try:
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    import pytz
except ModuleNotFoundError:
    print("Mendapati dependensi belum lengkap. Menginstal secara otomatis...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "apscheduler==3.10.4", "pytz"])
    from apscheduler.schedulers.asyncio import AsyncIOScheduler
    import pytz

# ====================================================================
# INITIALIZATION & INTENTS CONFIGURATION
# ====================================================================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True  

bot = commands.Bot(command_prefix="!", intents=intents)

JAKARTA_TZ = pytz.timezone("Asia/Jakarta")
# Mengunci timezone langsung pada inisialisasi scheduler global
scheduler = AsyncIOScheduler(timezone=JAKARTA_TZ)

# ====================================================================
# CONFIGURATION CONSTANTS
# ====================================================================
GUILD_ID = 1351182942625337378            
ID_CHANNEL_LOG_LOA = 1510642659776266442  
ID_ROLE_LOA = 1469270847905730590         
DATA_FILE = "loa_data.json"

ID_ROLE_PEMERINTAH = 1354869839692562523   
ID_CHANNEL_ANNOUNCEMENT = 1400173631421546620 

SERVER_CHANNELS = {
    "1": 1351207506612846638,
    "2": 1351210046599462945,
    "3": 1469229327219425334
}

ALLOWED_ROLE_SESSION_IDS = [
    1508831415461220423, 
    1351203409692463135, 
    1434199488398102688  
]

loa_system_active = True

# ====================================================================
# LOCAL DATABASE HELPER FUNCTIONS
# ====================================================================
def load_loa_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try: return json.load(f)
            except json.JSONDecodeError: return {}
    return {}

def save_loa_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

# ====================================================================
# ANTI-CRASH HELPER: MENCARI MEMBER DAN KONVERSI MENJADI TAG MENTION
# ====================================================================
def convert_to_user_mention(guild, input_text):
    if not guild or not input_text:
        return input_text
        
    input_text = input_text.strip()
    
    match_id = re.search(r'\d+', input_text)
    if match_id and ("<@" in input_text or len(input_text) >= 17):
        return f"<@{match_id.group()}>"
        
    clean_name = input_text.replace("@", "").split("|")[-1].strip().lower()
    
    for member in guild.members:
        if member.display_name.lower() == clean_name:
            return member.mention
        if member.name.lower() == clean_name:
            return member.mention
        if clean_name in member.display_name.lower() or clean_name in member.name.lower():
            return member.mention
            
    return input_text

# ====================================================================
# AUTOMATIC CHECKER TASK FOR EXPIRED LOA
# ====================================================================
@tasks.loop(hours=1.0)
async def check_expired_loa():
    guild = bot.get_guild(GUILD_ID)
    if not guild: return
    role_loa = guild.get_role(ID_ROLE_LOA)
    if not role_loa: return
    loa_data = load_loa_data()
    now = datetime.now(JAKARTA_TZ)
    updated = False
    for member_id_str, details in list(loa_data.items()):
        try:
            end_date = datetime.strptime(details["end_date"], "%d/%m/%Y")
            if now.date() > end_date.date():
                member_id = int(member_id_str)
                member = guild.get_member(member_id)
                if member and role_loa in member.roles:
                    try:
                        await member.remove_roles(role_loa)
                        embed_dm = discord.Embed(
                            title="Notice of LOA Termination",
                            description=(
                                f"Hello {member.mention},\n\n"
                                f"This is an official notification to inform you that your Leave of Absence (LOA) "
                                f"period has concluded. Your LOA role has been removed, and you are expected to "
                                f"resume your standard duties and responsibilities.\n\n"
                                f"**Thank you for your cooperation and welcome back.**"
                            ),
                            color=discord.Color(0x0d50b8)
                        )
                        await member.send(embed=embed_dm)
                    except Exception: pass
                del loa_data[member_id_str]
                updated = True
        except ValueError: continue
    if updated: save_loa_data(loa_data)

# ====================================================================
# LEAVE OF ABSENCE COMPONENT SCHEMAS
# ====================================================================
class RejectReasonModal(discord.ui.Modal, title="LOA Rejection Reason"):
    reason = discord.ui.TextInput(label="Reason for Rejection", placeholder="e.g. Input administrative rejection grounds here...", style=discord.TextStyle.long, required=True, max_length=300)
    
    def __init__(self, member_id: int, interaction_admin: discord.Interaction, view_approval):
        super().__init__()
        self.member_id = member_id
        self.interaction_admin = interaction_admin
        self.view_approval = view_approval
        
    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID: return
        await interaction.response.defer()
        
        guild = interaction.guild
        member = guild.get_member(self.member_id)
        
        embed = self.interaction_admin.message.embeds[0]
        embed.color = discord.Color.red()
        embed.title = "LOA REQUEST - REJECTED"
        embed.add_field(name="Reason for Rejection", value=self.reason.value, inline=False)
        
        await self.interaction_admin.message.edit(embed=embed, view=self.view_approval)
        
        if member:
            try:
                embed_dm = discord.Embed(
                    title="Your LOA Request Has Been Rejected",
                    description=(
                        f"Hello {member.mention},\n\n"
                        f"We regret to inform you that your Leave of Absence (LOA) request has been "
                        f"reviewed and rejected by the administration.\n\n"
                        f"**Reason for Rejection**\n"
                        f"{self.reason.value}\n\n"
                        f"Please contact the President or Vice President for further clarification."
                    ),
                    color=discord.Color.red()
                )
                await member.send(embed=embed_dm)
            except Exception: pass

class AdminApprovalView(discord.ui.View):
    def __init__(self, member_id: int, data_form: dict):
        super().__init__(timeout=None)
        self.member_id = member_id
        self.data_form = data_form
        
    @discord.ui.button(label="Accept Request", style=discord.ButtonStyle.success, custom_id="approve_loa_v14")
    async def approve_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != GUILD_ID: return
        await interaction.response.defer()
        guild = interaction.guild
        member = guild.get_member(self.member_id)
        
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.green()
        embed.title = "LOA REQUEST - APPROVED"
        
        for child in self.children: child.disabled = True
        await interaction.message.edit(embed=embed, view=self)
        
        if member:
            role_loa = guild.get_role(ID_ROLE_LOA)
            if role_loa:
                try: await member.add_roles(role_loa)
                except discord.Forbidden: pass
            
            loa_data = load_loa_data()
            loa_data[str(self.member_id)] = {"username": self.data_form["username"], "end_date": self.data_form["end_date"]}
            save_loa_data(loa_data)
            
            try:
                embed_dm = discord.Embed(
                    title="Your LOA Request Has Been Approved",
                    description=(
                        f"Hello {member.mention},\n\n"
                        f"Your Leave of Absence (LOA) request has been successfully reviewed and "
                        f"approved by the administration.\n\n"
                        f"**End Date**\n"
                        f"{self.data_form['end_date']}\n\n"
                        f"The Leave of Absence role has been assigned. System will auto-remove it once concluded."
                    ),
                    color=discord.Color.green()
                )
                await member.send(embed=embed_dm)
            except Exception: pass

    @discord.ui.button(label="Reject Request", style=discord.ButtonStyle.danger, custom_id="reject_loa_v14")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != GUILD_ID: return
        for child in self.children: child.disabled = True
        await interaction.response.send_modal(RejectReasonModal(member_id=self.member_id, interaction_admin=interaction, view_approval=self))

class LOAForm(discord.ui.Modal, title="Leave of Absence Application"):
    q1 = discord.ui.TextInput(label="1. Roblox Username", placeholder="Please enter your Roblox username.
", required=True, max_length=50)
    q2 = discord.ui.TextInput(label="2. Position / Department", placeholder="Please enter your position or department.
", required=True, max_length=70)
    q3 = discord.ui.TextInput(label="3. LOA End Date Only (Format: DD/MM/YYYY)", placeholder="Please enter the end date of your Leave of Absence (LOA). *(e.g., 01/06/2026)*.
", required=True, max_length=15)
    q4 = discord.ui.TextInput(label="4. Reason & Notes", placeholder="Please provide the reason and any additional notes regarding your leave request.
", style=discord.TextStyle.long, required=True, max_length=400)
    q5 = discord.ui.TextInput(label="5. Reachable during leave? (Yes / No)", placeholder="Please provide a response using **Yes** or **No** only.
", required=True, max_length=300)
    
    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID: return
        member = interaction.user
        await interaction.response.defer(ephemeral=True)
        
        try: datetime.strptime(self.q3.value.strip(), "%d/%m/%Y")
        except ValueError:
            await interaction.followup.send("Submission failed! Invalid date format. Use DD/MM/YYYY.", ephemeral=True)
            return
            
        log_channel = bot.get_channel(ID_CHANNEL_LOG_LOA)
        if log_channel:
            embed = discord.Embed(title="PENDING LOA REQUEST", description=f"Submission from {member.mention}", color=discord.Color(0x0d50b8))
            embed.add_field(name="1. Roblox Username", value=self.q1.value, inline=True)
            embed.add_field(name="2. Position / Department", value=self.q2.value, inline=True)
            embed.add_field(name="3. LOA End Date", value=self.q3.value, inline=True)
            embed.add_field(name="4. Reason & Notes", value=self.q4.value, inline=False)
            embed.add_field(name="5. Reachable during leave?", value=self.q5.value, inline=False)
            
            await log_channel.send(embed=embed, view=AdminApprovalView(member_id=member.id, data_form={"username": self.q1.value, "end_date": self.q3.value}))
            await interaction.followup.send("Your LOA request has been securely submitted.", ephemeral=True)

class LOAButtonView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Create LOA", style=discord.ButtonStyle.secondary, custom_id="button_create_loa_v14")
    async def create_loa_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id != GUILD_ID: return
        if not loa_system_active: return await interaction.response.send_message("The LOA system has been temporarily disabled.", ephemeral=True)
        await interaction.response.send_modal(LOAForm())

# ====================================================================
# AUTOMATED SCHEDULER EXECUTIONS (CRON JOBS)
# ====================================================================
async def send_staff_join_reminder(aorp_loc, server_code):
    print(f"[CRON RUN] Menjalankan tugas pengiriman pengingat staff join ({datetime.now()})")
    channel = bot.get_channel(ID_CHANNEL_ANNOUNCEMENT)
    if channel:
        reminder_text = (
            f"<@&{ID_ROLE_PEMERINTAH}>\n"
            f"AORP: {aorp_loc}\n"
            f"Server Code: {server_code}\n\n"
            f"Notes:\n"
            f"- Anda memiliki waktu 10 menit sejak kode ini dibagikan untuk join ke server, apabila Anda tidak join dalam waktu 10 menit tanpa keterangan yang jelas, Anda akan mendapatkan warning\n"
            f"- Gunakan seragam kerja Rise Country.\n"
            f"- Gunakan plat dinas Rise Country.\n"
            f"- Sistem akan secara otomatis mengirim format ke Server 1, 2, dan 3 sesuai waktu yang ditentukan. Mohon untuk sudah standby di STS 5 menit sebelum waktu pembukaan server roleplay."
        )
        await channel.send(content=reminder_text)
        print("[CRON SUCCESS] Pengingat staff join terkirim ke Discord.")
    else:
        print("[CRON ERROR] Channel Announcement tidak ditemukan!")

async def send_open_server_strict_template(target_channel_id, host_tag, map_author, aorp_loc, server_code):
    print(f"[CRON RUN] Menjalankan tugas pengiriman Open Server template ({datetime.now()})")
    channel = bot.get_channel(target_channel_id)
    if channel:
        template = (
            f"# **RiseCountry 🔴 STRICT RP**\n"
            f"**AORP : {aorp_loc}**\n"
            f"--------------------\n"
            f"Host : {host_tag}\n"
            f"Moderator : Staff RCRP\n"
            f"Map by : {map_author}\n"
            f"--------------------\n"
            f"**SERVICE CALL**\n"
            f"**911** POLISI\n"
            f"**119** AMBULAN\n"
            f"**112** PEMADAM\n"
            f"--------------------\n"
            f"**JOBS**\n"
            f"- Sopir Taxi\n"
            f"- Sopir Bus\n"
            f"- Sopir Truk\n"
            f"- Teknisi Bengkel\n"
            f"- Pedagang\n"
            f"- DLL\n"
            f"--------------------\n"
            f"**BANNED CARS**\n"
            f"- Strobo & Emergency  [Host and Staff only]\n"
            f"- Mobil Diatas 5M\n"
            f"- Limited (Selain Mobil In-House/Officially Tuned, Contoh: Brabus, Gemballa, Nismo, Ruf, etc)\n"
            f"--------------------\n"
            f"**ROLEPLAY RULES**\n"
            f"- Memakai Sein\n"
            f"- Menabrak Wajib \"Exc\"\n"
            f"- Mengikuti Rambu Lalu Lintas\n"
            f"- Auto Flip Car OFF\n"
            f"- Kunci Kendaraan\n"
            f"- PvP ON\n"
            f"- LOR Allowed\n"
            f"- Collision ON\n"
            f"- Dilarang Road Spawning\n"
            f"- Dilarang Menggunakan Plat Merah / Plat Polisi / Plat Militer\n"
            f"- Tidak Menggunakan Lajur Busway\n"
            f"--------------------\n"
            f"**SPEED LIMIT**\n"
            f"- Max Speed : 85\n"
            f"- Max Speed Gang : 30\n"
            f"--------------------\n"
            f"**FRP**\n"
            f"1x = Warn\n"
            f"2x = Kick\n"
            f"3x = Ban\n"
            f"--------------------\n"
            f"Code : {server_code}\n"
            f"Game Link :\n"
            f"https://www.roblox.com/games/6911148748/UPDATE-Car-Driving-Indonesia"
        )
        await channel.send(content=template)
        print(f"[CRON SUCCESS] Template Open Server terkirim ke Channel ID: {target_channel_id}")
    else:
        print(f"[CRON ERROR] Channel Target ID {target_channel_id} tidak ditemukan!")

# ====================================================================
# TWO-STAGE CONFIGURATION MODAL SYSTEM
# ====================================================================
class SessionPlannerPage2Modal(discord.ui.Modal, title="Page 2: Milestone Configurations"):
    f_staff = discord.ui.TextInput(label="1) Staff Join Time (HH.MM)", placeholder="Please enter the Staff Join Time.", style=discord.TextStyle.short, required=True)
    f_open = discord.ui.TextInput(label="2) Open Server Time (HH.MM)", placeholder="Please enter the Open Server Time.", style=discord.TextStyle.short, required=True)
    f_sts = discord.ui.TextInput(label="3) STS Time (HH.MM)", placeholder="Please enter the STS Time.", style=discord.TextStyle.short, required=True)
    f_rp_start = discord.ui.TextInput(label="4) Roleplay Start Time (HH.MM)", placeholder="Please enter the Roleplay Start Time.", style=discord.TextStyle.short, required=True)
    f_end = discord.ui.TextInput(label="5) End Session Time (HH.MM)", placeholder="Please enter the End Session Time.", style=discord.TextStyle.short, required=True)

    def __init__(self, data_p1: dict):
        super().__init__()
        self.data_p1 = data_p1

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID: return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        
        host_tag = convert_to_user_mention(guild, self.data_p1['host'])
        map_author_tag = convert_to_user_mention(guild, self.data_p1['map_author'])
        
        # PERBAIKAN STRIP & VALIDASI PARSING: Menggunakan regex murni menghindari bug karakter aneh
        staff_clean = re.sub(r'[^0-9.]', '', self.f_staff.value.strip().replace(":", "."))
        open_clean = re.sub(r'[^0-9.]', '', self.f_open.value.strip().replace(":", "."))
        
        try:
            s_hour, s_minute = map(int, staff_clean.split('.'))
        except Exception: 
            return await interaction.followup.send("Failed: Invalid format for Staff Join Time. Use HH.MM configuration.", ephemeral=True)

        try:
            o_hour, o_minute = map(int, open_clean.split('.'))
        except Exception: 
            return await interaction.followup.send("Failed: Invalid format for Open Server Time. Use HH.MM configuration.", ephemeral=True)

        session_time_computed = f"{self.f_open.value.strip()} - {self.f_end.value.strip()}"

        announcement_text = (
            f"__**Rise Country**__\n \n"
            f"{host_tag}\n"
            f"{self.data_p1['day_date']}\n"
            f"<@&{ID_ROLE_PEMERINTAH}> | @everyone\n \n"
            f"__**Schedule**__\n \n"
            f"Open Server : {self.f_open.value.strip()}\n"
            f"STS : {self.f_sts.value.strip()}\n"
            f"Roleplay Start : {self.f_rp_start.value.strip()}\n"
            f"Staff Join Time : {self.f_staff.value.strip()}\n"
            f"End Session : {self.f_end.value.strip()}\n \n"
            f"Session time : {session_time_computed} (GMT +7)\n \n"
            f"Note :\n"
            f"• Minimum requirement: 5 staff\n"
            f"• Please join at the scheduled time.\n"
            f"• The schedule may change at any time."
        )

        announcement_channel = bot.get_channel(ID_CHANNEL_ANNOUNCEMENT)
        if announcement_channel:
            # Jadwal Utama Langsung Dikirim Saat Itu Juga
            await announcement_channel.send(announcement_text)
            
            # PEMBERSIHAN ANTRIAN SAMA: Hapus ID lama jika bertumpuk demi kestabilan memori
            try: scheduler.remove_job(f"sj_cron_{interaction.user.id}")
            except Exception: pass
            try: scheduler.remove_job(f"os_cron_{interaction.user.id}")
            except Exception: pass

            # PENJADWALAN AMAN: Memakai trigger 'cron' dengan parameter timezone murni terenkapsulasi
            scheduler.add_job(
                send_staff_join_reminder, 
                'cron', 
                hour=s_hour, 
                minute=s_minute,
                timezone=JAKARTA_TZ,
                args=[self.data_p1['aorp'], self.data_p1['code']], 
                id=f"sj_cron_{interaction.user.id}"
            )
            
            chosen_channel_id = SERVER_CHANNELS[self.data_p1['channel']]
            scheduler.add_job(
                send_open_server_strict_template, 
                'cron', 
                hour=o_hour, 
                minute=o_minute,
                timezone=JAKARTA_TZ,
                args=[chosen_channel_id, host_tag, map_author_tag, self.data_p1['aorp'], self.data_p1['code']], 
                id=f"os_cron_{interaction.user.id}"
            )
            
            # Print log untuk verifikasi di terminal hosting kamu
            print(f"[SCHEDULER LOG] Berhasil dipasang untuk {interaction.user.name}:")
            print(f" -> Staff Join target jam {s_hour}:{s_minute} WIB (ID: sj_cron_{interaction.user.id})")
            print(f" -> Open Server target jam {o_hour}:{o_minute} WIB (ID: os_cron_{interaction.user.id})")

            success_embed = discord.Embed(
                title="Scheduler Activated Successfully!",
                description=(
                    f"• Main Schedule has been published with corrected user tagging.\n"
                    f"• Staff Join Reminder has been scheduled for {s_hour:02d}:{s_minute:02d} WIB.\n"
                    f"• Strict Roleplay Template has been scheduled for {o_hour:02d}:{o_minute:02d} WIB in Channel {self.data_p1['channel']}."
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)
        else:
            await interaction.followup.send("Failed: Operational announcement channel configuration missing.", ephemeral=True)

class SessionPlannerPage1Modal(discord.ui.Modal, title="Page 1: Identity & Parameters"):
    f_host = discord.ui.TextInput(label="Host Name", placeholder="Please enter the host's Discord username.", required=True, max_length=100)
    f_map = discord.ui.TextInput(label="Map Author Credit", placeholder="Please enter the host's Discord username.", required=True, max_length=100)
    f_day_date = discord.ui.TextInput(label="Day & Date", placeholder="Please enter the day and date *(e.g., Monday, 01 June 2026).*", required=True, max_length=100)
    f_aorp = discord.ui.TextInput(label="AORP Location / City", placeholder="Please enter the AORP.", required=True, max_length=100)
    f_code = discord.ui.TextInput(label="Server Private Code / Link", placeholder="Please enter the private server code.", required=True, max_length=200)

    def __init__(self, selected_channel: str):
        super().__init__()
        self.selected_channel = selected_channel

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID: return
        data_p1 = {
            "host": self.f_host.value.strip(), "map_author": self.f_map.value.strip(),
            "day_date": self.f_day_date.value.strip(), "aorp": self.f_aorp.value.strip(),
            "code": self.f_code.value.strip(), "channel": self.selected_channel
        }

        class NextStageView(discord.ui.View):
            def __init__(self): super().__init__(timeout=120)
            @discord.ui.button(label="Proceed to Milestone Configuration", style=discord.ButtonStyle.primary, custom_id="btn_stage_2_exec")
            async def open_p2(self, inner_interaction: discord.Interaction, button: discord.ui.Button):
                if inner_interaction.guild_id != GUILD_ID: return
                await inner_interaction.response.send_modal(SessionPlannerPage2Modal(data_p1=data_p1))

        transition_embed = discord.Embed(description="Initial parameters recorded. Please proceed to the next stage to configure session timestamps.", color=discord.Color(0x0d50b8))
        await interaction.response.send_message(embed=transition_embed, view=NextStageView(), ephemeral=True)

class ChannelSelectComponent(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Channel 1", value="1", description="Route strict session output to Server 1"),
            discord.SelectOption(label="Channel 2", value="2", description="Route strict session output to Server 2"),
            discord.SelectOption(label="Channel 3", value="3", description="Route strict session output to Server 3"),
        ]
        super().__init__(placeholder="Select Target Strict RP Channel...", min_values=1, max_values=1, options=options, custom_id="sel_channel_v14")

    async def callback(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID: return
        await interaction.response.send_modal(SessionPlannerPage1Modal(selected_channel=self.values[0]))

class WizardTriggerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ChannelSelectComponent())

# ====================================================================
# MANAGEMENT & SECURITY COMMANDS
# ====================================================================
@bot.command(name="setsession")
async def start_session_planner(ctx):
    if ctx.guild is None or ctx.guild.id != GUILD_ID: return
    user_roles = [role.id for role in ctx.author.roles]
    has_permission = ctx.author.guild_permissions.administrator or any(role_id in user_roles for role_id in ALLOWED_ROLE_SESSION_IDS)
    if not has_permission: return

    trigger_embed = discord.Embed(title="Session Scheduling Portal", description="Please use the menu below to configure and manage all scheduled session milestones.", color=discord.Color(0x0d50b8))
    await ctx.send(embed=trigger_embed, view=WizardTriggerView())

@bot.command(name="end_loa")
@commands.has_permissions(administrator=True)
async def remove_loa_manual(ctx, member: discord.Member = None):
    if ctx.guild is None or ctx.guild.id != GUILD_ID: return
    if member is None:
        return await ctx.send("Error. Please enter a valid staff username or ID.")

    guild = ctx.guild
    role_loa = guild.get_role(ID_ROLE_LOA)
    
    if role_loa and role_loa in member.roles:
        try: await member.remove_roles(role_loa)
        except discord.Forbidden: return await ctx.send(f"Error. Access request for {member.mention} has failed.")
    
    loa_data = load_loa_data()
    member_id_str = str(member.id)
    if member_id_str in loa_data:
        del loa_data[member_id_str]
        save_loa_data(loa_data)
    
    await ctx.send(f"LOA period has been successfully terminated for **{member.display_name}**. Role removed.")
    
    try:
        embed_dm = discord.Embed(
            title="Notice of LOA Termination",
            description=(
                f"Hello {member.mention},\n\n"
                f"This is an official notification to inform you that your Leave of Absence (LOA) "
                f"period has concluded. Your LOA role has been removed, and you are expected to "
                f"resume your standard duties and responsibilities.\n\n"
                f"**Thank you for your cooperation and welcome back.**"
            ),
            color=discord.Color(0x0d50b8)
        )
        await member.send(embed=embed_dm)
    except Exception: pass

@bot.command(name="loasystem")
@commands.has_permissions(administrator=True)
async def toggle_loa_system(ctx, status: str = None):
    if ctx.guild is None or ctx.guild.id != GUILD_ID: return
    global loa_system_active
    if status is None:
        current_status = "ENABLED" if loa_system_active else "DISABLED"
        return await ctx.send(f"⚙️ **LOA System Status:** `{current_status}`")
    if status.lower() == "off":
        loa_system_active = False
        await ctx.send("The Leave of Absence (LOA) system has been temporarily disabled. Please await further notice regarding its reactivation.")
    elif status.lower() == "on":
        loa_system_active = True
        await ctx.send("The Leave of Absence (LOA) system has been reactivated.")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_loa(ctx):
    if ctx.guild is None or ctx.guild.id != GUILD_ID: return
    embed = discord.Embed(
        title="Leave of Absence (LOA) Portal", 
        description=(
            "Welcome to the Leave of Absence System.\n\n"
            "This system is intended for members who require a temporary leave from their "
            "duties and responsibilities. Please submit your request with a clear reason and an "
            "accurate duration of absence.\n\n"
            "All submissions will be reviewed by the President or Vice President. Requests "
            "containing false information or any misuse of this system may result in disciplinary "
            "action in accordance with applicable regulations.\n\n"
            "The outcome of your LOA request will be sent to you via Direct Message (DM) "
            "once it has been reviewed and approved by the President or Vice President.\n\n"
            "Thank you for your cooperation and professionalism."
        ), 
        color=discord.Color(0x0d50b8)
    )
    await ctx.send(embed=embed, view=LOAButtonView())

# ====================================================================
# GLOBAL EVENT LISTENERS & INITIAL READINESS HANDLERS
# ====================================================================
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.MissingPermissions): return
    raise error

@bot.event
async def on_ready():
    bot.add_view(LOAButtonView())
    bot.add_view(WizardTriggerView()) 
    
    guild = bot.get_guild(GUILD_ID)
    if guild:
        try:
            await guild.chunk()
            print("Server member cache synchronized successfully.")
        except Exception as e:
            print(f"Warning on chunking: {e}")

    if not check_expired_loa.is_running(): check_expired_loa.start()
    if not scheduler.running: scheduler.start()
    print(f"Sistem Keamanan Aktif. {bot.user} dikunci penuh di Server ID: {GUILD_ID}.")

token = os.getenv('DISCORD_TOKEN')
if token: bot.run(token)
else: print("ERROR: DISCORD_TOKEN is missing.")
