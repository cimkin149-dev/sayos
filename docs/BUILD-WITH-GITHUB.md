# Build the ISO with GitHub (no Linux machine needed)

GitHub's servers build the ISO for free and hand you the download. If the build fails, they also hand
you the log, and you paste the last lines to Claude to get it fixed.

Public repositories get unlimited build time. Private repositories get 2,000 free minutes a month,
and one build takes roughly 60 minutes.

## 1. Put the project on GitHub
1. Sign in at github.com and create a new repository named `saymy-os` (Public is simplest).
2. Easiest and safest: install **GitHub Desktop**, choose *Add local repository* for the unzipped
   `saymy-os` folder, then *Publish repository*. This keeps the hidden `.github` folder and the correct
   line endings (the `.gitattributes` file handles that).
3. Web-only alternative: on the repository page choose *Add file, Upload files* and drag in the
   *contents* of the unzipped folder. Many browsers skip hidden folders, so afterwards choose
   *Add file, Create new file*, type `.github/workflows/build-iso.yml` as the name, and paste in the
   contents of that file from the zip.

## 2. Start the build
Open the **Actions** tab, pick **Build SayMy OS ISO**, press **Run workflow**. The quick checks
finish in about a minute; the ISO build takes 45 to 90 minutes. You can close the tab.

## 3. Get the result
- Green tick: open the finished run, scroll to *Artifacts*, download **saymy-os-iso** (a zip holding the ISO).
- Red cross: open the failed step, or download **saymy-os-build-logs**, and send Claude the last 60 lines.
  First builds usually need one or two small fixes (a package name, an option). That is normal.

## 4. Try the ISO safely
The live session installs nothing. Use **balenaEtcher** or **Rufus** to write the ISO to a USB stick,
boot a spare computer from it (usually F12, F10 or Esc at power-on), and look around.
Or install the free **VirtualBox**: new machine, Linux / Debian 64-bit, 4 GB RAM, 2 CPUs, boot from the ISO.
Do not press *Install SayMy OS* on a computer that holds data you care about until you have
done it once in a virtual machine.

## 5. Make a release
Tag the code `v0.1.0` and push the tag. The workflow then publishes the ISO on the repository's
*Releases* page so anyone can download it.
