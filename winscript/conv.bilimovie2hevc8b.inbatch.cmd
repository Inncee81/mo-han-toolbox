@echo off
setlocal

set args=%*
call set args=%%args:*%1=%%
if defined args set args=%args:* =%

conv.hevc8b.inbatch %1 -vf scale=1280:-2 -crf 25 %args%