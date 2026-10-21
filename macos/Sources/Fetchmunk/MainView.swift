import SwiftUI

let fetchmunkAccent = Color(red:0.91,green:0.39,blue:0.22)
struct MainView: View {
    @ObservedObject var model: AppModel
    @FocusState private var urlFocused: Bool
    var body: some View {
        NavigationSplitView {
            VStack(alignment:.leading,spacing:26) {
                HStack(spacing:10) {
                    Image(systemName:"arrow.down.circle.fill").font(.system(size:29)).foregroundStyle(fetchmunkAccent)
                    Text("Fetchmunk").font(.system(size:20,weight:.bold,design:.rounded))
                }.padding(.top,22)
                VStack(spacing:5) {
                    sidebarItem("Wszystkie",icon:"tray.full",tag:"all",count:model.totalCount)
                    sidebarItem("W kolejce",icon:"arrow.down.circle",tag:"active",count:model.activeCount)
                    sidebarItem("Historia",icon:"clock",tag:"history",count:model.historyCount)
                }
                Spacer()
                VStack(alignment:.leading,spacing:8) {
                    Label(model.ready ? "Silnik gotowy" : model.connecting ? "Uruchamianie silnika…" : "Silnik niedostępny",systemImage:model.ready ? "checkmark.circle.fill" : "circle.dotted")
                        .font(.caption).foregroundStyle(model.ready ? Color.secondary : fetchmunkAccent)
                    Text("Lokalnie. Bez konta.").font(.caption2).foregroundStyle(.tertiary)
                    Text("Wersja rozwojowa · 0.1.0").font(.caption2).foregroundStyle(.tertiary)
                }.padding(.bottom,18)
            }.padding(.horizontal,18).frame(maxHeight:.infinity).navigationSplitViewColumnWidth(min:190,ideal:210,max:240)
        } detail: {
            VStack(alignment:.leading,spacing:0) {
                HStack(alignment:.firstTextBaseline) {
                    VStack(alignment:.leading,spacing:5) {
                        Text("Z linku prosto na dysk.").font(.system(size:27,weight:.bold,design:.rounded))
                        Text("Wklej adres galerii lub pliku. Resztą zajmie się Fetchmunk.").font(.subheadline).foregroundStyle(.secondary)
                    }
                    Spacer()
                    if model.completedCount>0 { Label("\(model.completedCount) gotowych",systemImage:"checkmark.circle").font(.caption).foregroundStyle(.secondary) }
                }.padding(.bottom,24)
                VStack(alignment:.leading,spacing:14) {
                    HStack(spacing:12) {
                        Image(systemName:"link").foregroundStyle(.secondary)
                        TextField("https://…",text:$model.inputURL).textFieldStyle(.plain).font(.system(size:14))
                            .focused($urlFocused).onSubmit { Task { await model.add() } }.accessibilityLabel("Adres galerii lub pliku")
                        Button { Task { await model.add() } } label: {
                            HStack(spacing:7) { Image(systemName:"arrow.down");Text(model.adding ? "Dodawanie…" : "Pobierz") }.padding(.horizontal,10).padding(.vertical,5)
                        }.buttonStyle(.borderedProminent).tint(fetchmunkAccent)
                            .disabled(!model.ready || model.adding || model.inputURL.trimmingCharacters(in:.whitespacesAndNewlines).isEmpty)
                    }
                    Divider()
                    HStack {
                        Image(systemName:"folder").foregroundStyle(fetchmunkAccent)
                        Text(model.destination.path.replacingOccurrences(of:FileManager.default.homeDirectoryForCurrentUser.path,with:"~"))
                            .font(.caption).foregroundStyle(.secondary).lineLimit(1).truncationMode(.middle).help(model.destination.path)
                        Spacer()
                        Button("Zmień…") { model.chooseDestination() }.buttonStyle(.plain).font(.caption).foregroundStyle(fetchmunkAccent)
                    }
                }.padding(18).background(.background,in:RoundedRectangle(cornerRadius:14))
                    .overlay(RoundedRectangle(cornerRadius:14).stroke(Color.primary.opacity(0.08),lineWidth:1))
                if let message=model.message {
                    HStack(alignment:.top,spacing:9) {
                        Image(systemName:"exclamationmark.circle").foregroundStyle(fetchmunkAccent)
                        Text(message).font(.callout).textSelection(.enabled)
                        Spacer()
                        if !model.ready && !model.connecting { Button("Uruchom ponownie") { Task { await model.start() } } }
                        Button { model.message=nil } label: { Image(systemName:"xmark") }.buttonStyle(.plain).accessibilityLabel("Zamknij komunikat")
                    }.padding(12).background(fetchmunkAccent.opacity(0.08),in:RoundedRectangle(cornerRadius:10)).padding(.top,12)
                }
                HStack {
                    Text(model.selection=="history" ? "HISTORIA" : "POBIERANIE").font(.system(size:11,weight:.semibold)).tracking(1.4).foregroundStyle(.secondary)
                    Spacer()
                    if model.activeCount>0 {
                        Button(model.queueEnabled ? "Wstrzymaj kolejkę" : "Kontynuuj kolejkę") { Task { await model.toggleQueue() } }
                            .buttonStyle(.plain).font(.caption).disabled(!model.ready)
                            .help("Kontroluje rozpoczynanie kolejnych zadań. Nie wstrzymuje aktywnego transferu.")
                    }
                }.padding(.top,26).padding(.bottom,12)
                if let job = model.currentJob {
                    Text("TERAZ POBIERANE").font(.caption).foregroundStyle(.secondary)
                    JobRow(job:job,model:model).padding(.bottom,12)
                }
                HStack {
                    if model.history.loading { ProgressView().controlSize(.small) }
                    if model.history.stale {
                        Button("Lista została zaktualizowana · Odśwież") { Task { await model.loadPage(preserveAnchor:true) } }
                            .buttonStyle(.plain).font(.caption).foregroundStyle(fetchmunkAccent)
                    }
                    Spacer()
                    Button("Nowsze") { Task { await model.loadPage(cursor:model.history.previousCursor) } }
                        .disabled(!model.ready || model.history.loading || model.history.previousCursor == nil)
                    Button("Starsze") { Task { await model.loadPage(cursor:model.history.nextCursor) } }
                        .disabled(!model.ready || model.history.loading || model.history.nextCursor == nil)
                }.padding(.bottom,12)
                if model.visibleJobs.isEmpty {
                    VStack(spacing:14) {
                        Image(systemName:"tray.and.arrow.down").font(.system(size:43,weight:.light)).foregroundStyle(fetchmunkAccent.opacity(0.75))
                        Text(model.selection=="all" ? "Twoje pliki zaczynają się od linku." : "Tutaj jeszcze nic nie ma.").font(.system(size:17,weight:.medium,design:.rounded))
                        Text("Bez terminala. Bez ręcznej konfiguracji.").font(.subheadline).foregroundStyle(.secondary)
                        if model.selection=="all" { Text("Ten build obsługuje publiczne źródła. Logowanie pojawi się później.").font(.caption).foregroundStyle(.tertiary).multilineTextAlignment(.center) }
                    }.frame(maxWidth:.infinity,maxHeight:.infinity).padding(30)
                } else {
                    ScrollView {
                        LazyVStack(spacing:10) { ForEach(model.visibleJobs) { job in JobRow(job:job,model:model) } }.padding(.bottom,20)
                    }
                }
            }.padding(28).frame(minWidth:570,minHeight:500).background(Color(nsColor:.windowBackgroundColor))
        }.frame(minWidth:800,minHeight:560).onAppear { urlFocused=true }
    }
    private func sidebarItem(_ title:String,icon:String,tag:String,count:Int) -> some View {
        Button { Task { await model.select(tag) } } label: {
            HStack(spacing:10) {
                Image(systemName:icon).frame(width:19)
                Text(title);Spacer();Text("\(count)").font(.caption).monospacedDigit().foregroundStyle(.secondary)
            }.font(.system(size:13,weight:model.selection==tag ? .semibold : .regular)).padding(.horizontal,11).padding(.vertical,10)
                .background(model.selection==tag ? fetchmunkAccent.opacity(0.12) : .clear,in:RoundedRectangle(cornerRadius:8))
                .foregroundStyle(model.selection==tag ? fetchmunkAccent : .primary)
        }.buttonStyle(.plain)
    }
}
