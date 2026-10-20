import SwiftUI
struct JobRow: View {
    let job: Job
    @ObservedObject var model: AppModel
    var color: Color { job.state=="completed" ? .green : ["failed","partial","needs_auth"].contains(job.state) ? fetchmunkAccent : .secondary }
    var body: some View {
        HStack(alignment:.top,spacing:14) {
            Image(systemName:job.state=="completed" ? "checkmark.circle.fill" : job.isActive ? "arrow.down.circle" : "photo.on.rectangle")
                .font(.system(size:23,weight:.light)).foregroundStyle(color).frame(width:34,height:36)
            VStack(alignment:.leading,spacing:7) {
                HStack(alignment:.firstTextBaseline) {
                    Text(job.title.isEmpty ? job.host : job.title).font(.system(size:13,weight:.semibold)).lineLimit(1)
                    Spacer();Text(job.status).font(.caption).foregroundStyle(color)
                }
                Text(job.host).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                if job.isActive {
                    if let f=job.current_file, let total=f.bytes_total, total>0 { ProgressView(value:Double(f.bytes_done),total:Double(total)).tint(fetchmunkAccent) }
                    else { ProgressView().controlSize(.small).frame(maxWidth:.infinity,alignment:.leading) }
                }
                HStack {
                    Text("Pobrano \(job.downloaded) · pominięto \(job.skipped)" + (job.failed_files>0 ? " · błędy \(job.failed_files)" : ""))
                        .font(.caption2).foregroundStyle(.secondary).monospacedDigit()
                    Spacer()
                    if job.canCancel { Button("Anuluj") { Task { await model.jobAction("jobs.cancel",job:job) } }.disabled(job.state=="cancelling") }
                    if job.canRetry { Button("Ponów") { Task { await model.jobAction("jobs.retry",job:job) } } }
                    if job.downloaded+job.skipped>0 { Button { model.reveal(job) } label: { Image(systemName:"folder") }.help("Pokaż pliki").accessibilityLabel("Pokaż pliki") }
                }.buttonStyle(.borderless).font(.caption).disabled(!model.ready || model.pendingJobs.contains(job.id))
                if let error=job.error { Text(errorMessage(error.code)).font(.caption).foregroundStyle(fetchmunkAccent).textSelection(.enabled) }
            }
        }.padding(16).background(.background,in:RoundedRectangle(cornerRadius:12))
            .overlay(RoundedRectangle(cornerRadius:12).stroke(Color.primary.opacity(0.06),lineWidth:1))
    }
}
