import AppKit
import Vision

var processed = false
for path in CommandLine.arguments.dropFirst() {
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    if let revision = VNRecognizeTextRequest.supportedRevisions.max() {
        req.revision = revision
    }
    if let supported = try? VNRecognizeTextRequest.supportedRecognitionLanguages(for: .accurate, revision: req.revision) {
        let preferred = ["zh-Hans", "en-US"].filter { supported.contains($0) }
        if !preferred.isEmpty { req.recognitionLanguages = preferred }
    }
    let handler = VNImageRequestHandler(url: URL(fileURLWithPath: path), options: [:])
    guard (try? handler.perform([req])) != nil else { continue }
    processed = true
    let observations = (req.results ?? []).compactMap { $0 as? VNRecognizedTextObservation }
    if observations.contains(where: {
        ($0.topCandidates(1).first?.string.trimmingCharacters(in: CharacterSet.whitespaces).count ?? 0) >= 4
    }) {
        print("found")
        exit(0)
    }
}
print(processed ? "not-found" : "unavailable")
