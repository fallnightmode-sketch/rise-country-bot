# ====================================================================
# HELPER: FUNGSI UNTUK MENGUBAH INPUT TEKS MENJADI MENTION/TAG UTUH
# ====================================================================
def convert_to_user_mention(guild, input_text):
    input_text = input_text.strip()
    if not input_text:
        return "Not Specified"
        
    # Skenario 1: Jika user langsung melakukan mention di modal (format: <@123456789>)
    match_id = re.search(r'\d+', input_text)
    if match_id and ("<@" in input_text or len(input_text) >= 17):
        return f"<@{match_id.group()}>"
        
    # Skenario 2: Jika user mengetik teks biasa (misal: Doctor_BYP atau @PRES | Doctor_BYP)
    # Kita bersihkan dulu simbol '@' dan pemisah internal jika ada
    clean_name = input_text.replace("@", "").split("|")[-1].strip()
    
    # Cari member di server yang nama display, nama global, atau username-nya cocok
    member = discord.utils.get(guild.members, display_name=clean_name)
    if not member:
        member = discord.utils.get(guild.members, name=clean_name)
    
    # Jika ketemu, kembalikan dalam bentuk tag <@ID>, jika tidak ketemu kembalikan teks asli
    if member:
        return member.mention
    return input_text


# ====================================================================
# UPDATE: PROSES PENANGANAN MODAL PAGE 2 (KIRIM TEMPLATE LENGKAP)
# ====================================================================
class SessionPlannerPage2Modal(discord.ui.Modal, title="Page 2: Milestone Configurations"):
    f_staff = discord.ui.TextInput(label="1) Staff Join Time (HH.MM)", placeholder="e.g. 16.27", style=discord.TextStyle.short, required=True)
    f_open = discord.ui.TextInput(label="2) Open Server Time (HH.MM)", placeholder="e.g. 16.28", style=discord.TextStyle.short, required=True)
    f_sts = discord.ui.TextInput(label="3) STS Time (HH.MM)", placeholder="e.g. 16.29", style=discord.TextStyle.short, required=True)
    f_rp_start = discord.ui.TextInput(label="4) Roleplay Start Time (HH.MM)", placeholder="e.g. 17.00", style=discord.TextStyle.short, required=True)
    f_end = discord.ui.TextInput(label="5) End Session Time (HH.MM)", placeholder="e.g. 17.01", style=discord.TextStyle.short, required=True)

    def __init__(self, data_p1: dict):
        super().__init__()
        self.data_p1 = data_p1

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.guild_id != GUILD_ID: return
        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        
        # Eksekusi konversi otomatis menjadi format Tag/Mention (<@ID>)
        host_tag = convert_to_user_mention(guild, self.data_p1['host'])
        map_author_tag = convert_to_user_mention(guild, self.data_p1['map_author'])
        
        staff_raw = self.f_staff.value.strip().replace(":", ".")
        try: s_hour, s_minute = map(int, "".join([c for c in staff_raw if c.isdigit() or c == '.']).split('.'))
        except Exception: return await interaction.followup.send("Failed: Invalid format for Staff Join Time. Use HH.MM configuration.", ephemeral=True)

        open_raw = self.f_open.value.strip().replace(":", ".")
        try: o_hour, o_minute = map(int, "".join([c for c in open_raw if c.isdigit() or c == '.']).split('.'))
        except Exception: return await interaction.followup.send("Failed: Invalid format for Open Server Time. Use HH.MM configuration.", ephemeral=True)

        session_time_computed = f"{self.f_open.value.strip()} - {self.f_end.value.strip()}"

        # Format teks pengumuman utama
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
            await announcement_channel.send(announcement_text)
            
            # Daftarkan cron job otomatis untuk reminder staff
            scheduler.add_job(send_staff_join_reminder, 'cron', hour=s_hour, minute=s_minute, args=[self.data_p1['aorp'], self.data_p1['code']], id=f"sj_cron_{interaction.id}")
            
            # Daftarkan cron job untuk mengirim format Strict RP ke target channel dengan tag yang sudah diperbaiki
            chosen_channel_id = SERVER_CHANNELS[self.data_p1['channel']]
            scheduler.add_job(send_open_server_strict_template, 'cron', hour=o_hour, minute=o_minute, args=[chosen_channel_id, host_tag, map_author_tag, self.data_p1['aorp'], self.data_p1['code']], id=f"os_cron_{interaction.id}")
            
            success_embed = discord.Embed(
                title="Scheduler Activated Successfully!",
                description=(
                    f"• Main Schedule has been published with corrected user tagging.\n"
                    f"• Staff Join Reminder has been scheduled for {self.f_staff.value.strip()} WIB.\n"
                    f"• Strict Roleplay Template has been scheduled for {self.f_open.value.strip()} WIB in Channel {self.data_p1['channel']}."
                ),
                color=discord.Color.green()
            )
            await interaction.followup.send(embed=success_embed, ephemeral=True)
        else:
            await interaction.followup.send("Failed: Operational announcement channel configuration missing.", ephemeral=True)
