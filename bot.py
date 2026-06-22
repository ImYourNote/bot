import os
import math
import random

import discord
from discord import app_commands
from dotenv import load_dotenv

# .env 파일에서 환경변수(봇 토큰 등)를 불러온다.
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# 팀별로 이동시킬 음성 채널 이름 (서버에 이 이름 그대로 음성 채널을 만들어 두세요).
# 팀1 -> 첫 번째 이름, 팀2 -> 두 번째 이름 ... 순서로 이동합니다.
TEAM_CHANNEL_NAMES = [
    "🎮┆스 쿼 드❶",
    "🎮┆스 쿼 드❷",
    "🎮┆스 쿼 드❸",
]

# 인텐트 설정: 음성 채널 멤버 정보를 읽으려면 members 인텐트가 필요하다.
intents = discord.Intents.default()
intents.members = True
intents.voice_states = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def split_teams(members, max_per_team=4):
    """
    members 리스트를 최대한 균등하게 팀으로 나눈다.

    - 필요한 팀 수 = 올림(인원 / 최대인원)
    - 그 팀 수로 인원을 최대한 똑같이 분배
    예) 6명, max=4 -> 2팀 -> [3, 3]
        10명, max=4 -> 3팀 -> [4, 3, 3]
        9명, max=4 -> 3팀 -> [3, 3, 3]
    """
    shuffled = members[:]
    random.shuffle(shuffled)

    n = len(shuffled)
    if n == 0:
        return []

    num_teams = math.ceil(n / max_per_team)

    # 각 팀 기본 인원 = n // num_teams,
    # 나머지(remainder)만큼 앞쪽 팀에 1명씩 추가 -> 최대한 균등
    base = n // num_teams
    remainder = n % num_teams

    teams = []
    idx = 0
    for t in range(num_teams):
        size = base + (1 if t < remainder else 0)
        teams.append(shuffled[idx:idx + size])
        idx += size

    return teams


class MoveButton(discord.ui.View):
    """
    '음성 채널로 이동' 버튼이 달린 View.
    버튼을 누르면 각 팀원을 미리 만들어둔 '팀N' 음성 채널로 이동시킨다.
    """

    def __init__(self, teams, guild):
        super().__init__(timeout=300)  # 5분 후 버튼 비활성화
        self.teams = teams
        self.guild = guild

    @discord.ui.button(label="음성 채널로 이동", style=discord.ButtonStyle.primary, emoji="🔀")
    async def move(self, interaction: discord.Interaction, button: discord.ui.Button):
        # 권한 체크: 멤버 이동 권한이 있는 사람만 누를 수 있게
        if not interaction.user.guild_permissions.move_members:
            await interaction.response.send_message(
                "❌ 멤버 이동 권한이 있는 사람만 이 버튼을 사용할 수 있어요.",
                ephemeral=True,
            )
            return

        moved = 0
        not_found_channels = []

        for i, team in enumerate(self.teams):
            # 미리 정해둔 채널 이름 리스트에서 i번째 이름을 가져온다.
            if i < len(TEAM_CHANNEL_NAMES):
                channel_name = TEAM_CHANNEL_NAMES[i]
            else:
                # 팀 수가 정해둔 채널 이름보다 많은 경우
                not_found_channels.append(f"(팀{i + 1}용 채널 이름이 부족함)")
                continue

            # 서버에서 해당 이름의 음성 채널을 찾는다.
            target = discord.utils.get(
                self.guild.voice_channels, name=channel_name
            )
            if target is None:
                not_found_channels.append(channel_name)
                continue

            for member in team:
                # 멤버가 아직 음성 채널에 있을 때만 이동 가능
                if member.voice and member.voice.channel:
                    try:
                        await member.move_to(target)
                        moved += 1
                    except discord.HTTPException:
                        pass

        msg = f"✅ {moved}명을 각 팀 음성 채널로 이동시켰어요."
        if not_found_channels:
            missing = ", ".join(not_found_channels)
            msg += (
                f"\n⚠️ 다음 음성 채널을 찾지 못했어요: **{missing}**\n"
                f"서버에 해당 이름의 음성 채널을 미리 만들어 주세요."
            )

        await interaction.response.send_message(msg, ephemeral=True)


@client.event
async def on_ready():
    await tree.sync()
    print(f"로그인 완료: {client.user} (봇 준비됨)")


@tree.command(name="팀나누기", description="음성 채널 인원을 랜덤으로 팀을 나눕니다.")
@app_commands.describe(최대인원="한 팀의 최대 인원 (기본값 4)")
async def divide_teams(interaction: discord.Interaction, 최대인원: int = 4):
    # 명령어를 친 사람이 음성 채널에 있는지 확인
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message(
            "❌ 먼저 음성 채널에 들어간 뒤 명령어를 사용해 주세요.",
            ephemeral=True,
        )
        return

    if 최대인원 < 1:
        await interaction.response.send_message(
            "❌ 최대 인원은 1명 이상이어야 해요.", ephemeral=True
        )
        return

    voice_channel = interaction.user.voice.channel
    # 봇을 제외한 실제 사람 멤버만 대상으로
    members = [m for m in voice_channel.members if not m.bot]

    if len(members) == 0:
        await interaction.response.send_message(
            "❌ 음성 채널에 나눌 인원이 없어요.", ephemeral=True
        )
        return

    teams = split_teams(members, max_per_team=최대인원)

    # 결과 텍스트 만들기
    lines = [f"🎮 **팀 나누기 결과** (총 {len(members)}명, 최대 {최대인원}명 기준)\n"]
    for i, team in enumerate(teams):
        names = ", ".join(m.display_name for m in team)
        # 해당 팀이 이동할 채널 이름을 함께 보여준다.
        if i < len(TEAM_CHANNEL_NAMES):
            channel_label = TEAM_CHANNEL_NAMES[i]
        else:
            channel_label = f"(채널 부족)"
        lines.append(f"**{channel_label}** ({len(team)}명): {names}")

    result_text = "\n".join(lines)

    view = MoveButton(teams, interaction.guild)
    # ephemeral=False -> 모두가 볼 수 있게 출력
    await interaction.response.send_message(result_text, view=view)


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit(
            "DISCORD_TOKEN 환경변수가 설정되지 않았어요. .env 파일을 확인해 주세요."
        )
    client.run(TOKEN)