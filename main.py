import asyncio
import discord
import os
import yaml
from config import Settings
from audiosource import FFmpegRTPSource, FFmpegRTPSink
from pyVoIP.VoIP import VoIPPhone, InvalidStateError, CallState, VoIPCall

if os.environ.get("VOIPCORD_ENVCONFIG"):
    settings = Settings()  # Exclusively use environment variables for configuration.
elif os.path.exists(os.environ.get('CONFIG', "config.yml")):
    config = yaml.safe_load(open(os.environ.get('CONFIG', "config.yml"), encoding="utf8"))
    settings = Settings.parse_obj(config)
else:
    print(f"No config file was found at {os.environ.get('CONFIG', 'config.yml')}, failing over to environment "
          "variables.\nIf this was intentional, set VOIPCORD_ENVCONFIG=true to hide this warning.")
    settings = Settings()

print('VoIPcord\nhttps://github.com/samicrusader/voipcord', end='\n--\n')
phone = VoIPPhone(server=settings.voip.server, port=settings.voip.port, username=settings.voip.username,
                  password=settings.voip.password)

intents = discord.Intents.default()
intents.members = True
intents.messages = True
intents.message_content = True
client = discord.Bot(test_guilds=[settings.discord.home_guild_id], intents=intents, prefix='!')
voip_commands = client.create_group('phone', 'Telephony commands')
mgmt_commands = client.create_group('voipcord', 'Management commands')
connections = {}
calls = {}


@client.event
async def on_ready():
    print(f'Logged in as {client.user.name}#{client.user.discriminator} ({client.user.id})')
    await asyncio.to_thread(phone.start)
    print(phone.get_status())
    print(await client.sync_commands())


@client.event
async def on_application_command_error(ctx: discord.ApplicationContext, error):
    await ctx.respond(str(error), ephemeral=True)
    raise error


async def stub_callback(sink, channel: discord.TextChannel, *args):
    return


@voip_commands.command(name='call', description='call number', ephemeral=True,
                       guild_ids=[settings.discord.home_guild_id])
async def dial(ctx, number: discord.Option(discord.SlashCommandOptionType.string)):
    # setup voice
    if not ctx.author.voice:
        return await ctx.respond('join the vc you fuckwit', ephemeral=True)
    vc = await ctx.author.voice.channel.connect()
    connections.update({ctx.guild.id: vc})

    # dial number
    call = await asyncio.to_thread(phone.call, number)
    await ctx.defer(ephemeral=True)  # tell discord we'll be a minute

    # wait for call answer or fail
    while True:
        await asyncio.sleep(0.1)
        if call.state == CallState.ENDED:
            await ctx.respond('Call failed.', ephemeral=True)
            return
        if call.state == CallState.ANSWERED:
            break
    # caller answered, shit out call state and setup audio
    try:
        await ctx.respond('Call answered!', ephemeral=True)
        vc.start_recording(FFmpegRTPSink(call), stub_callback, ctx.channel)
        source = FFmpegRTPSource(source=call)
        vc.play(source)
        calls.update({ctx.guild.id: call})
        while call.state == CallState.ANSWERED:
            await asyncio.sleep(0.1)
    except InvalidStateError as e:
        await ctx.respond('Caller disconnected.', ephemeral=True)
        return


@voip_commands.command(name='hook', description='hang up phone', ephemeral=True,
                       guild_ids=[settings.discord.home_guild_id])
async def hangup(ctx):
    if ctx.guild.id not in calls.keys():
        return await ctx.respond('Phone is not engaged in a call.', ephemeral=True)
    vc: discord.VoiceClient = connections[ctx.guild.id]
    call: VoIPCall = calls[ctx.guild.id]
    vc.stop_recording()
    vc.stop()
    try:
        call.hangup()
    except InvalidStateError:
        await ctx.respond('Phone was already on-hook.', ephemeral=True)
        return
    else:
        return await ctx.respond('Phone is now on-hook.', ephemeral=True)
    finally:
        del connections[ctx.guild.id]
        await vc.disconnect(force=True)

try:
    client.run(settings.discord.token)
except:
    client.close()
    phone.stop()
