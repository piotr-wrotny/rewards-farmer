# Runtime Info

## Host

| | |
|---|---|
| Hostname | `puse-wpbos-bobr` (10.17.103.115) |
| Arch | x86_64 |
| OS | Ubuntu 26.04 LTS, kernel 7.0.0-22-generic |
| CPU / RAM | 8 vCPU / 15 GB |
| Docker | 29.4.1 |
| Disk | 96 GB (73 GB wolne) |

## Binder (wymagany przez ReDroid)

```bash
sudo modprobe binder_linux devices=binder,hwbinder,vndbinder
sudo mkdir -p /dev/binderfs && sudo mount -t binder binder /dev/binderfs
echo binder_linux | sudo tee /etc/modules-load.d/binder.conf
```

Weryfikacja: `ls /dev/binderfs` → `binder binder-control features hwbinder vndbinder`.
Bez tego kontener boot-loopuje (init żyje, zygote restarting, hwservicemanager zombie).

## ReDroid

| | |
|---|---|
| Obraz | `redroid/redroid:14.0.0-latest` (amd64) |
| Android | 14 (SDK 34), ABI x86_64 (+ arm64-v8a w abilist — ARM translation) |
| Uruchomienie | `docker run -d --name redroid --privileged -p 127.0.0.1:5555:5555 -v ~/redroid-data:/data redroid/redroid:14.0.0-latest androidboot.redroid_gpu_mode=guest` |
| Boot czas | ~45 s do `sys.boot_completed=1` |

## ADB

Tunel SSH (port hosta bound do 127.0.0.1 — bezpieczne):

```bash
ssh -N -L 15555:127.0.0.1:5555 piotr.wrotny@10.17.103.115 &
adb connect 127.0.0.1:15555
```

## Locale (Bing po angielsku)

```bash
adb -s 127.0.0.1:15555 shell "setprop persist.sys.locale en-US; setprop ctl.restart zygote"
```

## Bing

| | |
|---|---|
| Package | `com.microsoft.bing` |
| Wersja | `34.0.440821002` (global; arm64-v8a) |
| Źródło APK | `assets/Microsoft+Bing+Search_34.0.440821002_APKPure.apk` (APKPure) |
| Instalacja | `adb install -r <apk>` — Success |
| Launcher | `com.microsoft.sapphire.app.main.SapphireMainActivity` |

## Sieć — ZNANE OGRANICZENIE

- Host: HTTP egress OK (`curl https://www.bing.com` → 200), ICMP blokowane przez sieć firmową.
- Kontener ReDroid: **brak DNS** — `net.dns1`/`net.dns2` puste, webview → `ERR_NAME_NOT_RESOLVED`.
- Root cause: Docker bridge nie propaguje DNS hosta (172.20.0.41/42) do Androida.

### Naprawa DNS (do wykonania przy odtworzeniu)

Opcja A — props przy starcie kontenera:
```
docker run ... redroid/redroid:14.0.0-latest \
  androidboot.redroid_gpu_mode=guest \
  androidboot.redroid_net_dns1=172.20.0.41 \
  androidboot.redroid_net_dns2=172.20.0.42
```
Opcja B — przez `adb shell setprop net.dns1 172.20.0.41` (wymaga restartu netd).
**Niezweryfikowane** — zaznaczone jako follow-up.
